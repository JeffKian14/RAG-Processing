import os
import time
import requests

from src.chunking.chunk_test_utils import (
    FORMATS, get_corpus_files, parse_source,
    validate_common_chunk_fields, collect_common_chunk_stats,
    merge_error_counts, token_summary
)

from src.chunking.units import build_chunk_units
from src.chunking.semantic_chunker_v2 import chunk_document, MIN_TOKENS, TARGET_TOKENS, MAX_TOKENS, BREAKPOINT_PERCENTILE, MODEL_NAME
from src.chunking.utils import longest_common_hierarchy


MODEL_URL = "http://localhost:1234/v1/models"
PROGRESS_EVERY = 10


def new_stats():
    return {
        "docs": 0,
        "chunks": 0,
        "tokens": [],
        "under_50": 0,
        "under_80": 0,
        "under_100": 0,
        "100_199": 0,
        "200_299": 0,
        "300_399": 0,
        "equal_400": 0,
        "over_350": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0
    }


def new_errors():
    return {
        "failed": 0,
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
        "content_loss": 0,
        "oversize": 0,
        "determinism_err": 0,
        "hier_err": 0,
        "page_err": 0,
        "slide_err": 0
    }


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def print_progress(done: int, total: int, started: float, fmt: str):
    elapsed = time.perf_counter() - started

    if done <= 0:
        return

    average_per_doc = elapsed / done
    eta = average_per_doc * (total - done)
    estimated_total = average_per_doc * total
    percent = done / total * 100 if total else 100.0

    print(
        f"[{done}/{total}] {percent:5.1f}% | "
        f"Current: {fmt:<4} | "
        f"Elapsed {format_seconds(elapsed)} | "
        f"ETA {format_seconds(eta)} | "
        f"Est. total {format_seconds(estimated_total)}",
        flush=True
    )


def check_lm_studio():
    try:
        response = requests.get(MODEL_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"LM Studio server is unavailable: {e}") from e

    try:
        payload = response.json()
    except ValueError as e:
        raise RuntimeError("LM Studio /v1/models returned invalid JSON") from e

    models = [model.get("id") for model in payload.get("data", [])]

    if MODEL_NAME not in models:
        raise RuntimeError(f"Embedding model '{MODEL_NAME}' is not loaded. Loaded models: {models}")


def safe_token_summary(tokens):
    if not tokens: return 0, 0.0, 0
    minimum, average, maximum = token_summary(tokens)
    return minimum, average, maximum


def run_tests():
    print("=" * 72)
    print("PHASE 8G-2: SEMANTIC CHUNKING V2 VALIDATION")
    print("=" * 72)
    print(f"Embedding model: {MODEL_NAME}")
    print("Embedding server: http://localhost:1234")
    print(f"Min / Target / Max: {MIN_TOKENS} / {TARGET_TOKENS} / {MAX_TOKENS}")
    print(f"Semantic distance percentile: {BREAKPOINT_PERCENTILE}")
    print("=" * 72)

    check_lm_studio()

    corpus_files = []

    for path in get_corpus_files():
        fmt = os.path.splitext(path)[1][1:].upper()
        if fmt in FORMATS: corpus_files.append(path)

    total_documents = len(corpus_files)

    print(f"Documents to test: {total_documents}")
    print(f"Progress update every {PROGRESS_EVERY} documents")
    print("ETA becomes more accurate after the first few documents.")
    print("=" * 72)

    stats = {fmt: new_stats() for fmt in FORMATS}
    errors = {fmt: new_errors() for fmt in FORMATS}

    seen_ids = set()
    failures = []
    started = time.perf_counter()

    for document_number, path in enumerate(corpus_files, start=1):
        fmt = os.path.splitext(path)[1][1:].upper()
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path)
            units = build_chunk_units(doc)
            source_text = "\n\n".join(unit.text for unit in units)

            # ------------------------------------------------------------
            # Independent source spans for provenance checking
            # ------------------------------------------------------------

            unit_spans = []
            cursor = 0

            for i, unit in enumerate(units):
                if i > 0: cursor += 2

                start = cursor
                end = start + len(unit.text)

                unit_spans.append((start, end, unit))
                cursor = end

            # ------------------------------------------------------------
            # Run twice for determinism
            # The second call should mostly hit the embedding cache.
            # ------------------------------------------------------------

            chunks1 = chunk_document(doc)
            chunks2 = chunk_document(doc)

            if [chunk.model_dump() for chunk in chunks1] != [chunk.model_dump() for chunk in chunks2]:
                errors[fmt]["determinism_err"] += 1

            # ------------------------------------------------------------
            # Existing shared validation infrastructure
            # ------------------------------------------------------------

            common_errors = validate_common_chunk_fields(doc, chunks1, "semantic_v2", seen_ids)
            merge_error_counts(errors[fmt], common_errors)

            common_stats = collect_common_chunk_stats(chunks1)

            stats[fmt]["chunks"] += common_stats["chunks"]
            stats[fmt]["tokens"].extend(common_stats["tokens"])
            stats[fmt]["hier"] += common_stats["hier"]
            stats[fmt]["no_hier"] += common_stats["no_hier"]
            stats[fmt]["pages"] += common_stats["pages"]
            stats[fmt]["slides"] += common_stats["slides"]

            # ------------------------------------------------------------
            # Exact source reconstruction
            # ------------------------------------------------------------

            if "".join(chunk.text for chunk in chunks1) != source_text:
                errors[fmt]["content_loss"] += 1

            # ------------------------------------------------------------
            # V2-specific stats + independent provenance validation
            # ------------------------------------------------------------

            cursor = 0

            for chunk in chunks1:
                tokens = chunk.token_count

                if tokens > MAX_TOKENS: errors[fmt]["oversize"] += 1

                if tokens < 50: stats[fmt]["under_50"] += 1
                if tokens < 80: stats[fmt]["under_80"] += 1
                if tokens < 100: stats[fmt]["under_100"] += 1
                if 100 <= tokens < 200: stats[fmt]["100_199"] += 1
                if 200 <= tokens < 300: stats[fmt]["200_299"] += 1
                if 300 <= tokens < 400: stats[fmt]["300_399"] += 1
                if tokens == 400: stats[fmt]["equal_400"] += 1
                if tokens >= 350: stats[fmt]["over_350"] += 1

                chunk_start = cursor
                chunk_end = chunk_start + len(chunk.text)
                cursor = chunk_end

                contributors = [unit for start, end, unit in unit_spans if end > chunk_start and start < chunk_end]

                expected_hierarchy = longest_common_hierarchy([unit.section_hierarchy for unit in contributors]) if contributors else []

                pages = [unit.page_number for unit in contributors]
                slides = [unit.slide_number for unit in contributors]

                expected_page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
                expected_slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None

                if chunk.section_hierarchy != expected_hierarchy: errors[fmt]["hier_err"] += 1
                if chunk.page_number != expected_page: errors[fmt]["page_err"] += 1
                if chunk.slide_number != expected_slide: errors[fmt]["slide_err"] += 1

        except Exception as e:
            errors[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

        if document_number % PROGRESS_EVERY == 0 or document_number == total_documents:
            print_progress(document_number, total_documents, started, fmt)

    # ================================================================
    # PER FORMAT
    # ================================================================

    print("\n" + "=" * 72)
    print("PER-FORMAT RESULTS")
    print("=" * 72)

    for fmt in FORMATS:
        s = stats[fmt]
        e = errors[fmt]

        minimum, average, maximum = safe_token_summary(s["tokens"])
        average_chunks = s["chunks"] / s["docs"] if s["docs"] else 0
        under_80_percent = s["under_80"] / s["chunks"] * 100 if s["chunks"] else 0
        under_100_percent = s["under_100"] / s["chunks"] * 100 if s["chunks"] else 0

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {e['failed']}")
        print(f"Chunks: {s['chunks']}")
        print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
        print(f"Average chunks/document: {average_chunks:.2f}")
        print()
        print(f"Chunks <50: {s['under_50']}")
        print(f"Chunks <80: {s['under_80']} ({under_80_percent:.1f}%)")
        print(f"Chunks <100: {s['under_100']} ({under_100_percent:.1f}%)")
        print(f"Chunks 100-199: {s['100_199']}")
        print(f"Chunks 200-299: {s['200_299']}")
        print(f"Chunks 300-399: {s['300_399']}")
        print(f"Chunks =400: {s['equal_400']}")
        print(f"Chunks >=350: {s['over_350']}")
        print()
        print(f"Chunks with hierarchy: {s['hier']}")
        print(f"Chunks without hierarchy: {s['no_hier']}")
        print(f"Page-numbered chunks: {s['pages']}")
        print(f"Slide-numbered chunks: {s['slides']}")

    # ================================================================
    # TOTALS
    # ================================================================

    total_stats = new_stats()
    total_errors = new_errors()

    for fmt in FORMATS:
        total_stats["docs"] += stats[fmt]["docs"]
        total_stats["chunks"] += stats[fmt]["chunks"]
        total_stats["tokens"].extend(stats[fmt]["tokens"])

        for key in [
            "under_50", "under_80", "under_100",
            "100_199", "200_299", "300_399",
            "equal_400", "over_350",
            "hier", "no_hier", "pages", "slides"
        ]:
            total_stats[key] += stats[fmt][key]

        for key in total_errors:
            total_errors[key] += errors[fmt][key]

    minimum, average, maximum = safe_token_summary(total_stats["tokens"])
    average_chunks = total_stats["chunks"] / total_stats["docs"] if total_stats["docs"] else 0
    under_80_percent = total_stats["under_80"] / total_stats["chunks"] * 100 if total_stats["chunks"] else 0
    under_100_percent = total_stats["under_100"] / total_stats["chunks"] * 100 if total_stats["chunks"] else 0

    total_elapsed = time.perf_counter() - started

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total_stats['docs']}")
    print(f"Failed: {total_errors['failed']}")
    print(f"Chunks: {total_stats['chunks']}")
    print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
    print(f"Average chunks/document: {average_chunks:.2f}")
    print()
    print(f"Chunks <50: {total_stats['under_50']}")
    print(f"Chunks <80: {total_stats['under_80']} ({under_80_percent:.1f}%)")
    print(f"Chunks <100: {total_stats['under_100']} ({under_100_percent:.1f}%)")
    print(f"Chunks 100-199: {total_stats['100_199']}")
    print(f"Chunks 200-299: {total_stats['200_299']}")
    print(f"Chunks 300-399: {total_stats['300_399']}")
    print(f"Chunks =400: {total_stats['equal_400']}")
    print(f"Chunks >=350: {total_stats['over_350']}")
    print()
    print(f"Chunks with hierarchy: {total_stats['hier']}")
    print(f"Chunks without hierarchy: {total_stats['no_hier']}")
    print(f"Page-numbered chunks: {total_stats['pages']}")
    print(f"Slide-numbered chunks: {total_stats['slides']}")
    print()
    print(f"Empty chunks: {total_errors['empty']}")
    print(f"Duplicate IDs: {total_errors['dup_id']}")
    print(f"Index errors: {total_errors['idx_err']}")
    print(f"Method errors: {total_errors['method_err']}")
    print(f"Metadata errors: {total_errors['meta_err']}")
    print(f"Token-count errors: {total_errors['token_err']}")
    print(f"Chunk-ID errors: {total_errors['id_err']}")
    print()
    print(f"Content preservation errors: {total_errors['content_loss']}")
    print(f"Oversize errors: {total_errors['oversize']}")
    print(f"Determinism errors: {total_errors['determinism_err']}")
    print(f"Hierarchy errors: {total_errors['hier_err']}")
    print(f"Page provenance errors: {total_errors['page_err']}")
    print(f"Slide provenance errors: {total_errors['slide_err']}")
    print()
    print(f"Total elapsed time: {format_seconds(total_elapsed)}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")

        for failure in failures:
            print(f"  - {failure}")

    critical_keys = [
        "failed",
        "empty",
        "dup_id",
        "idx_err",
        "method_err",
        "meta_err",
        "token_err",
        "id_err",
        "content_loss",
        "oversize",
        "determinism_err",
        "hier_err",
        "page_err",
        "slide_err"
    ]

    critical_errors = sum(total_errors[key] for key in critical_keys)

    print()
    print(f"SEMANTIC CHUNKING V2 VALIDATION {'PASSED' if critical_errors == 0 else 'NEEDS REVIEW'}")
    print("=" * 72)


if __name__ == "__main__":
    run_tests()