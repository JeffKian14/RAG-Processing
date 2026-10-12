import os
import requests
from collections import defaultdict

from src.chunking.chunk_test_utils import (
    FORMATS, get_corpus_files, parse_source, validate_common_chunk_fields,
    collect_common_chunk_stats, merge_error_counts, token_summary
)
from src.chunking.units import build_chunk_units
from src.chunking.semantic_chunker import chunk_document, DEFAULT_MODEL_NAME
from src.chunking.utils import longest_common_hierarchy


MAX_TOKENS = 400
MODEL_NAME = DEFAULT_MODEL_NAME
MODEL_URL = "http://localhost:1234/v1/models"


def new_stats():
    return {
        "docs": 0, "failed": 0, "chunks": 0, "tokens": [],
        "empty": 0, "dup_id": 0, "idx_err": 0, "method_err": 0,
        "meta_err": 0, "token_err": 0, "id_err": 0,
        "content_loss": 0, "oversize": 0, "determinism_err": 0,
        "hier_err": 0, "page_err": 0, "slide_err": 0,
        "over_350": 0, "under_100": 0,
        "hier": 0, "no_hier": 0, "pages": 0, "slides": 0
    }


def check_lm_studio():
    try:
        response = requests.get(MODEL_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"LM Studio server is not available: {e}") from e

    models = [model["id"] for model in response.json().get("data", [])]

    if MODEL_NAME not in models:
        raise RuntimeError(f"Embedding model '{MODEL_NAME}' is not loaded in LM Studio. Loaded models: {models}")


def run_tests():
    print("=" * 72)
    print("PHASE 8G: SEMANTIC CHUNKING VALIDATION")
    print("=" * 72)
    print(f"Embedding model: {MODEL_NAME}")
    print("Embedding server: http://localhost:1234")
    print("=" * 72)

    check_lm_studio()

    stats = defaultdict(new_stats)
    failures = []
    seen_ids = set()

    for path in get_corpus_files():
        ext = os.path.splitext(path)[1].lower()
        fmt = ext[1:].upper()

        if fmt not in FORMATS: continue
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path)
            units = build_chunk_units(doc)
            source_text = "\n\n".join(u.text for u in units)

            # ------------------------------------------------------------
            # INDEPENDENT SOURCE SPANS
            # ------------------------------------------------------------

            unit_spans = []
            cursor = 0

            for i, unit in enumerate(units):
                if i > 0: cursor += 2
                unit_spans.append((cursor, cursor + len(unit.text), unit))
                cursor += len(unit.text)

            # ------------------------------------------------------------
            # RUN TWICE FOR DETERMINISM
            # ------------------------------------------------------------

            chunks1 = chunk_document(doc, max_tokens=MAX_TOKENS)
            chunks2 = chunk_document(doc, max_tokens=MAX_TOKENS)

            if [c.model_dump() for c in chunks1] != [c.model_dump() for c in chunks2]:
                stats[fmt]["determinism_err"] += 1

            # ------------------------------------------------------------
            # COMMON STATS + VALIDATION
            # ------------------------------------------------------------

            common_stats = collect_common_chunk_stats(chunks1)
            stats[fmt]["chunks"] += common_stats["chunks"]
            stats[fmt]["tokens"].extend(common_stats["tokens"])
            stats[fmt]["hier"] += common_stats["hier"]
            stats[fmt]["no_hier"] += common_stats["no_hier"]
            stats[fmt]["pages"] += common_stats["pages"]
            stats[fmt]["slides"] += common_stats["slides"]

            common_errors = validate_common_chunk_fields(doc, chunks1, "semantic", seen_ids)
            merge_error_counts(stats[fmt], common_errors)

            # ------------------------------------------------------------
            # EXACT CONTENT PRESERVATION
            # ------------------------------------------------------------

            if "".join(c.text for c in chunks1) != source_text:
                stats[fmt]["content_loss"] += 1

            # ------------------------------------------------------------
            # SEMANTIC-SPECIFIC VALIDATION
            # ------------------------------------------------------------

            cursor = 0

            for chunk in chunks1:
                if chunk.token_count > MAX_TOKENS: stats[fmt]["oversize"] += 1
                if chunk.token_count >= 350: stats[fmt]["over_350"] += 1
                if chunk.token_count < 100: stats[fmt]["under_100"] += 1

                start = cursor
                end = start + len(chunk.text)
                cursor = end

                contrib = [u for s, e, u in unit_spans if e > start and s < end]
                expected_hierarchy = longest_common_hierarchy([u.section_hierarchy for u in contrib]) if contrib else []

                pages = [u.page_number for u in contrib]
                slides = [u.slide_number for u in contrib]

                expected_page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
                expected_slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None

                if chunk.section_hierarchy != expected_hierarchy: stats[fmt]["hier_err"] += 1
                if chunk.page_number != expected_page: stats[fmt]["page_err"] += 1
                if chunk.slide_number != expected_slide: stats[fmt]["slide_err"] += 1

        except Exception as e:
            stats[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

    # ================================================================
    # PER-FORMAT
    # ================================================================

    for fmt in FORMATS:
        s = stats[fmt]
        minimum, average, maximum = token_summary(s["tokens"])
        avg_chunks = s["chunks"] / s["docs"] if s["docs"] else 0

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {s['failed']}")
        print(f"Chunks: {s['chunks']}")
        print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
        print(f"Average chunks/document: {avg_chunks:.2f}")
        print(f"Chunks >=350 tokens: {s['over_350']}")
        print(f"Chunks <100 tokens: {s['under_100']}")
        print(f"Page-numbered chunks: {s['pages']}")
        print(f"Slide-numbered chunks: {s['slides']}")

    # ================================================================
    # TOTALS
    # ================================================================

    total = {key: 0 for key in new_stats() if key != "tokens"}

    for fmt in FORMATS:
        for key in total: total[key] += stats[fmt][key]

    all_tokens = [token for fmt in FORMATS for token in stats[fmt]["tokens"]]
    minimum, average, maximum = token_summary(all_tokens)

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['docs']}")
    print(f"Failed: {total['failed']}")
    print(f"Chunks: {total['chunks']}")
    print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
    print()
    print(f"Empty chunks: {total['empty']}")
    print(f"Duplicate IDs: {total['dup_id']}")
    print(f"Index errors: {total['idx_err']}")
    print(f"Method errors: {total['method_err']}")
    print(f"Metadata errors: {total['meta_err']}")
    print(f"Token-count errors: {total['token_err']}")
    print(f"Chunk-ID errors: {total['id_err']}")
    print()
    print(f"Content preservation errors: {total['content_loss']}")
    print(f"Oversize errors: {total['oversize']}")
    print(f"Determinism errors: {total['determinism_err']}")
    print(f"Hierarchy errors: {total['hier_err']}")
    print(f"Page provenance errors: {total['page_err']}")
    print(f"Slide provenance errors: {total['slide_err']}")
    print()
    print(f"Chunks >=350: {total['over_350']}")
    print(f"Chunks <100: {total['under_100']}")
    print()
    print(f"Chunks with hierarchy: {total['hier']}")
    print(f"Chunks without hierarchy: {total['no_hier']}")
    print(f"Page-numbered chunks: {total['pages']}")
    print(f"Slide-numbered chunks: {total['slides']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures: print(f"  - {failure}")

    error_keys = [
        "failed", "empty", "dup_id", "idx_err", "method_err", "meta_err", "token_err", "id_err",
        "content_loss", "oversize", "determinism_err", "hier_err", "page_err", "slide_err"
    ]

    critical_errors = sum(total[key] for key in error_keys)

    print(f"\nSEMANTIC CHUNKING VALIDATION {'PASSED' if critical_errors == 0 else 'NEEDS REVIEW'}")
    print("=" * 72)


if __name__ == "__main__":
    run_tests()