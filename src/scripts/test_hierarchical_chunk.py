import os
import sys
import time

from src.chunking.chunk_test_utils import (
    FORMATS,
    get_corpus_files,
    parse_source,
    validate_common_chunk_fields,
    collect_common_chunk_stats,
    token_summary
)

from src.chunking.units import build_chunk_units
from src.chunking.hierarchical_chunker import (
    chunk_document,
    PARENT_MAX_TOKENS,
    CHILD_MAX_TOKENS
)

from src.chunking.utils import longest_common_hierarchy


PROGRESS_EVERY = 10


def new_stats():
    return {
        "docs": 0,

        "parent_count": 0,
        "child_count": 0,

        "parent_tokens": [],
        "child_tokens": [],

        "parent_under_100": 0,
        "parent_under_400": 0,
        "parent_400_599": 0,
        "parent_600_799": 0,
        "parent_800_999": 0,
        "parent_equal_1000": 0,

        "child_under_100": 0,
        "child_100_199": 0,
        "child_200_249": 0,
        "child_250_299": 0,
        "child_equal_300": 0,

        "parent_hier": 0,
        "parent_no_hier": 0,
        "parent_pages": 0,
        "parent_slides": 0,

        "child_hier": 0,
        "child_no_hier": 0,
        "child_pages": 0,
        "child_slides": 0,

        "parents_1_child": 0,
        "parents_2_children": 0,
        "parents_3_children": 0,
        "parents_4plus_children": 0
    }


def new_errors():
    return {
        "failed": 0,

        "parent_empty": 0,
        "parent_dup_id": 0,
        "parent_idx_err": 0,
        "parent_method_err": 0,
        "parent_meta_err": 0,
        "parent_token_err": 0,
        "parent_id_err": 0,

        "child_empty": 0,
        "child_dup_id": 0,
        "child_idx_err": 0,
        "child_method_err": 0,
        "child_meta_err": 0,
        "child_token_err": 0,
        "child_id_err": 0,

        "parent_oversize": 0,
        "child_oversize": 0,

        "parent_source_err": 0,
        "child_source_err": 0,

        "missing_parent_ref": 0,
        "multiple_parent_ownership": 0,
        "parent_child_id_mismatch": 0,
        "child_outside_parent": 0,
        "parent_reconstruction_err": 0,
        "child_reconstruction_err": 0,

        "parent_hierarchy_err": 0,
        "parent_page_err": 0,
        "parent_slide_err": 0,

        "child_hierarchy_err": 0,
        "child_page_err": 0,
        "child_slide_err": 0,

        "parent_determinism_err": 0,
        "child_determinism_err": 0
    }


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def print_progress(done: int, total: int, started: float):
    elapsed = time.perf_counter() - started
    average = elapsed / done if done else 0
    eta = average * (total - done)
    total_est = average * total

    sys.stdout.write(
        f"\r[{done}/{total}] {done / total * 100:5.1f}% | "
        f"Elapsed {format_seconds(elapsed)} | "
        f"ETA {format_seconds(eta)} | "
        f"Est. total {format_seconds(total_est)}"
    )

    sys.stdout.flush()


def add_common_errors(target: dict, prefix: str, common: dict):
    mapping = {
        "empty": f"{prefix}_empty",
        "dup_id": f"{prefix}_dup_id",
        "idx_err": f"{prefix}_idx_err",
        "method_err": f"{prefix}_method_err",
        "meta_err": f"{prefix}_meta_err",
        "token_err": f"{prefix}_token_err",
        "id_err": f"{prefix}_id_err"
    }

    for source, destination in mapping.items():
        target[destination] += common.get(source, 0)


def consensus(values):
    return values[0] if values and len(set(values)) == 1 and values[0] is not None else None


def build_unit_spans(units):
    spans = []
    cursor = 0

    for i, unit in enumerate(units):
        if i > 0: cursor += 2

        start = cursor
        end = start + len(unit.text)

        spans.append((start, end, unit))
        cursor = end

    return spans


def expected_metadata(start, end, unit_spans):
    contributors = [
        unit
        for unit_start, unit_end, unit in unit_spans
        if unit_end > start and unit_start < end
    ]

    if not contributors:
        return [], None, None

    hierarchy = longest_common_hierarchy([unit.section_hierarchy for unit in contributors])
    page = consensus([unit.page_number for unit in contributors])
    slide = consensus([unit.slide_number for unit in contributors])

    return hierarchy, page, slide


def validate_provenance(chunks, unit_spans, errors, prefix):
    cursor = 0

    for chunk in chunks:
        start = cursor
        end = start + len(chunk.text)

        hierarchy, page, slide = expected_metadata(start, end, unit_spans)

        if chunk.section_hierarchy != hierarchy: errors[f"{prefix}_hierarchy_err"] += 1
        if chunk.page_number != page: errors[f"{prefix}_page_err"] += 1
        if chunk.slide_number != slide: errors[f"{prefix}_slide_err"] += 1

        cursor = end


def validate_relationships(parents, children, errors):
    parent_map = {parent.chunk_id: parent for parent in parents}
    ownership = {}

    for parent in parents:
        for child_id in parent.child_chunk_ids:
            ownership[child_id] = ownership.get(child_id, 0) + 1

    for child in children:
        if child.parent_chunk_id not in parent_map:
            errors["missing_parent_ref"] += 1

        count = ownership.get(child.chunk_id, 0)

        if count == 0:
            errors["missing_parent_ref"] += 1
        elif count > 1:
            errors["multiple_parent_ownership"] += 1

    for parent in parents:
        assigned = [child for child in children if child.parent_chunk_id == parent.chunk_id]
        expected_ids = [child.chunk_id for child in assigned]

        if parent.child_chunk_ids != expected_ids:
            errors["parent_child_id_mismatch"] += 1

        reconstructed = "".join(child.text for child in assigned)

        if reconstructed != parent.text:
            errors["parent_reconstruction_err"] += 1
            errors["child_reconstruction_err"] += 1

        cursor = 0

        for child in assigned:
            end = cursor + len(child.text)

            if parent.text[cursor:end] != child.text:
                errors["child_outside_parent"] += 1

            cursor = end


def record_stats(stats, parents, children):
    p_common = collect_common_chunk_stats(parents)
    c_common = collect_common_chunk_stats(children)

    stats["parent_count"] += p_common["chunks"]
    stats["child_count"] += c_common["chunks"]

    stats["parent_tokens"].extend(p_common["tokens"])
    stats["child_tokens"].extend(c_common["tokens"])

    stats["parent_hier"] += p_common["hier"]
    stats["parent_no_hier"] += p_common["no_hier"]
    stats["parent_pages"] += p_common["pages"]
    stats["parent_slides"] += p_common["slides"]

    stats["child_hier"] += c_common["hier"]
    stats["child_no_hier"] += c_common["no_hier"]
    stats["child_pages"] += c_common["pages"]
    stats["child_slides"] += c_common["slides"]

    for parent in parents:
        tokens = parent.token_count

        if tokens < 100: stats["parent_under_100"] += 1
        if tokens < 400: stats["parent_under_400"] += 1
        elif tokens < 600: stats["parent_400_599"] += 1
        elif tokens < 800: stats["parent_600_799"] += 1
        elif tokens < 1000: stats["parent_800_999"] += 1
        elif tokens == 1000: stats["parent_equal_1000"] += 1

        count = len(parent.child_chunk_ids)

        if count == 1: stats["parents_1_child"] += 1
        elif count == 2: stats["parents_2_children"] += 1
        elif count == 3: stats["parents_3_children"] += 1
        elif count >= 4: stats["parents_4plus_children"] += 1

    for child in children:
        tokens = child.token_count

        if tokens < 100: stats["child_under_100"] += 1
        elif tokens < 200: stats["child_100_199"] += 1
        elif tokens < 250: stats["child_200_249"] += 1
        elif tokens < 300: stats["child_250_299"] += 1
        elif tokens == 300: stats["child_equal_300"] += 1


def safe_summary(tokens):
    if not tokens: return 0, 0.0, 0
    return token_summary(tokens)


def run_tests():
    print("=" * 72)
    print("PHASE 8H: HIERARCHICAL / PARENT-CHILD CHUNKING VALIDATION")
    print("=" * 72)
    print("Parent target/max: 800 / 1000")
    print("Child target/max: 220 / 300")
    print("Grouping: compatible top-level hierarchy")
    print("Overlap: 0")
    print("=" * 72)

    files = [
        path for path in get_corpus_files()
        if os.path.splitext(path)[1][1:].upper() in FORMATS
    ]

    stats = {fmt: new_stats() for fmt in FORMATS}
    errors = {fmt: new_errors() for fmt in FORMATS}

    seen_ids = set()
    failures = []
    started = time.perf_counter()

    for number, path in enumerate(files, start=1):
        fmt = os.path.splitext(path)[1][1:].upper()
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path)
            units = build_chunk_units(doc)
            source_text = "\n\n".join(unit.text for unit in units)
            unit_spans = build_unit_spans(units)

            parents1, children1 = chunk_document(doc)
            parents2, children2 = chunk_document(doc)

            if [p.model_dump() for p in parents1] != [p.model_dump() for p in parents2]:
                errors[fmt]["parent_determinism_err"] += 1

            if [c.model_dump() for c in children1] != [c.model_dump() for c in children2]:
                errors[fmt]["child_determinism_err"] += 1

            p_common = validate_common_chunk_fields(doc, parents1, "hierarchical_parent", seen_ids)
            c_common = validate_common_chunk_fields(doc, children1, "hierarchical_child", seen_ids)

            add_common_errors(errors[fmt], "parent", p_common)
            add_common_errors(errors[fmt], "child", c_common)

            if "".join(parent.text for parent in parents1) != source_text:
                errors[fmt]["parent_source_err"] += 1

            if "".join(child.text for child in children1) != source_text:
                errors[fmt]["child_source_err"] += 1

            for parent in parents1:
                if parent.token_count > PARENT_MAX_TOKENS: errors[fmt]["parent_oversize"] += 1
                if parent.parent_chunk_id is not None: errors[fmt]["parent_child_id_mismatch"] += 1

            for child in children1:
                if child.token_count > CHILD_MAX_TOKENS: errors[fmt]["child_oversize"] += 1
                if child.child_chunk_ids: errors[fmt]["parent_child_id_mismatch"] += 1

            validate_provenance(parents1, unit_spans, errors[fmt], "parent")
            validate_provenance(children1, unit_spans, errors[fmt], "child")
            validate_relationships(parents1, children1, errors[fmt])

            record_stats(stats[fmt], parents1, children1)

        except Exception as exc:
            errors[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(f"{fmt} | {os.path.basename(path)} | {type(exc).__name__}: {exc}")

        if number % PROGRESS_EVERY == 0 or number == len(files):
            print_progress(number, len(files), started)

    print()

    total_stats = new_stats()
    total_errors = new_errors()

    for fmt in FORMATS:
        total_stats["docs"] += stats[fmt]["docs"]
        total_stats["parent_count"] += stats[fmt]["parent_count"]
        total_stats["child_count"] += stats[fmt]["child_count"]
        total_stats["parent_tokens"].extend(stats[fmt]["parent_tokens"])
        total_stats["child_tokens"].extend(stats[fmt]["child_tokens"])

        for key in total_stats:
            if key in {"docs", "parent_count", "child_count", "parent_tokens", "child_tokens"}:
                continue
            total_stats[key] += stats[fmt][key]

        for key in total_errors:
            total_errors[key] += errors[fmt][key]

    print("\n" + "=" * 72)
    print("PER-FORMAT RESULTS")
    print("=" * 72)

    for fmt in FORMATS:
        s, e = stats[fmt], errors[fmt]

        p_min, p_avg, p_max = safe_summary(s["parent_tokens"])
        c_min, c_avg, c_max = safe_summary(s["child_tokens"])

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']} | Failed: {e['failed']}")
        print(f"Parents: {s['parent_count']} | Avg/Doc: {s['parent_count']/(s['docs'] or 1):.2f} | Min/Avg/Max: {p_min}/{p_avg:.1f}/{p_max}")
        print(f"Children: {s['child_count']} | Avg/Doc: {s['child_count']/(s['docs'] or 1):.2f} | Avg/Parent: {s['child_count']/(s['parent_count'] or 1):.2f} | Min/Avg/Max: {c_min}/{c_avg:.1f}/{c_max}")
        print(f"Parents <100: {s['parent_under_100']} | Parents <400: {s['parent_under_400']}")
        print(f"Children <100: {s['child_under_100']}")
        print(f"1-child parents: {s['parents_1_child']}")

    p_min, p_avg, p_max = safe_summary(total_stats["parent_tokens"])
    c_min, c_avg, c_max = safe_summary(total_stats["child_tokens"])

    elapsed = time.perf_counter() - started

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total_stats['docs']}")
    print(f"Failed: {total_errors['failed']}")

    print("\nPARENTS")
    print(f"Parents: {total_stats['parent_count']}")
    print(f"Average parents/document: {total_stats['parent_count']/(total_stats['docs'] or 1):.2f}")
    print(f"Min/Avg/Max tokens: {p_min} / {p_avg:.1f} / {p_max}")
    print(f"Parents <100: {total_stats['parent_under_100']}")
    print(f"Parents <400: {total_stats['parent_under_400']}")
    print(f"Parents 400-599: {total_stats['parent_400_599']}")
    print(f"Parents 600-799: {total_stats['parent_600_799']}")
    print(f"Parents 800-999: {total_stats['parent_800_999']}")
    print(f"Parents =1000: {total_stats['parent_equal_1000']}")

    print("\nCHILDREN")
    print(f"Children: {total_stats['child_count']}")
    print(f"Average children/document: {total_stats['child_count']/(total_stats['docs'] or 1):.2f}")
    print(f"Average children/parent: {total_stats['child_count']/(total_stats['parent_count'] or 1):.2f}")
    print(f"Min/Avg/Max tokens: {c_min} / {c_avg:.1f} / {c_max}")
    print(f"Children <100: {total_stats['child_under_100']}")
    print(f"Children 100-199: {total_stats['child_100_199']}")
    print(f"Children 200-249: {total_stats['child_200_249']}")
    print(f"Children 250-299: {total_stats['child_250_299']}")
    print(f"Children =300: {total_stats['child_equal_300']}")

    print("\nRELATIONSHIPS")
    print(f"Parents with 1 child: {total_stats['parents_1_child']}")
    print(f"Parents with 2 children: {total_stats['parents_2_children']}")
    print(f"Parents with 3 children: {total_stats['parents_3_children']}")
    print(f"Parents with 4+ children: {total_stats['parents_4plus_children']}")

    print("\nVALIDATION")
    for key, value in total_errors.items():
        print(f"{key}: {value}")

    print(f"\nTotal elapsed time: {format_seconds(elapsed)}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures: print(f"  - {failure}")

    critical_errors = sum(total_errors.values())

    print()
    print(f"HIERARCHICAL CHUNKING VALIDATION {'PASSED' if critical_errors == 0 else 'NEEDS REVIEW'}")
    print("=" * 72)


if __name__ == "__main__":
    run_tests()