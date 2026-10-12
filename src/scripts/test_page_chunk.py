import os
from collections import defaultdict

from src.chunking.units import build_chunk_units
from src.chunking.page_chunker import chunk_document
from src.chunking.chunk_test_utils import (
    get_corpus_files,
    parse_source,
    validate_common_chunk_fields,
    collect_common_chunk_stats,
    merge_error_counts,
    token_summary,
)


def new_stats():
    return {
        "docs": 0,
        "failed": 0,
        "chunks": 0,
        "tokens": [],
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
        "text_mismatch": 0,
        "chunk_count_mismatch": 0,
        "provenance_err": 0,
        "unit_loss": 0,
        "order_err": 0,
        "over_400": 0,
        "over_512": 0,
        "over_1024": 0,
        "over_2048": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0,
    }


def run_tests():
    print("=" * 72)
    print("PHASE 8E: PAGE/SLIDE CHUNKING VALIDATION")
    print("=" * 72)

    paths = [
        path
        for path in get_corpus_files()
        if os.path.splitext(path)[1].lower() in (".pdf", ".pptx")
    ]

    stats = defaultdict(new_stats)
    failures = []
    seen_ids = set()

    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        fmt = ext[1:].upper()
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path)
            units = build_chunk_units(doc)

            mode = "page" if fmt == "PDF" else "slide"

            # ------------------------------------------------------------
            # Build expected page/slide groups independently
            # ------------------------------------------------------------

            expected_groups = []

            if units:
                current_id = None
                current_group = []

                for unit in units:
                    provenance_id = (
                        unit.page_number
                        if mode == "page"
                        else unit.slide_number
                    )

                    if provenance_id is None:
                        raise ValueError(
                            f"Missing {mode} provenance in {os.path.basename(path)}"
                        )

                    if current_id is None:
                        current_id = provenance_id

                    if provenance_id == current_id:
                        current_group.append(unit)

                    else:
                        expected_groups.append(
                            (current_id, current_group)
                        )

                        current_id = provenance_id
                        current_group = [unit]

                if current_group:
                    expected_groups.append(
                        (current_id, current_group)
                    )

            # ------------------------------------------------------------
            # Run production chunker
            # ------------------------------------------------------------

            chunks = chunk_document(doc)

            # ------------------------------------------------------------
            # Common statistics
            # ------------------------------------------------------------

            common_stats = collect_common_chunk_stats(chunks)

            stats[fmt]["chunks"] += common_stats["chunks"]
            stats[fmt]["tokens"].extend(common_stats["tokens"])
            stats[fmt]["hier"] += common_stats["hier"]
            stats[fmt]["no_hier"] += common_stats["no_hier"]
            stats[fmt]["pages"] += common_stats["pages"]
            stats[fmt]["slides"] += common_stats["slides"]

            # ------------------------------------------------------------
            # Common chunk validation
            # ------------------------------------------------------------

            common_errors = validate_common_chunk_fields(
                doc,
                chunks,
                "page_slide",
                seen_ids,
            )

            merge_error_counts(stats[fmt], common_errors)

            # ------------------------------------------------------------
            # Chunk count validation
            # ------------------------------------------------------------

            if len(chunks) != len(expected_groups):
                stats[fmt]["chunk_count_mismatch"] += 1

            # ------------------------------------------------------------
            # Page/slide-specific validation
            # ------------------------------------------------------------

            for i, chunk in enumerate(chunks):
                if i >= len(expected_groups):
                    continue

                expected_id, expected_units = expected_groups[i]

                expected_text = "\n\n".join(
                    unit.text
                    for unit in expected_units
                )

                if chunk.text != expected_text:
                    stats[fmt]["text_mismatch"] += 1

                if mode == "page":
                    if (
                        chunk.page_number != expected_id
                        or chunk.slide_number is not None
                    ):
                        stats[fmt]["provenance_err"] += 1

                else:
                    if (
                        chunk.slide_number != expected_id
                        or chunk.page_number is not None
                    ):
                        stats[fmt]["provenance_err"] += 1

                if chunk.token_count > 400:
                    stats[fmt]["over_400"] += 1

                if chunk.token_count > 512:
                    stats[fmt]["over_512"] += 1

                if chunk.token_count > 1024:
                    stats[fmt]["over_1024"] += 1

                if chunk.token_count > 2048:
                    stats[fmt]["over_2048"] += 1

            # ------------------------------------------------------------
            # Whole-document preservation + ordering validation
            # ------------------------------------------------------------

            expected_document_text = "\n\n".join(
                unit.text
                for unit in units
            )

            actual_document_text = "\n\n".join(
                chunk.text
                for chunk in chunks
            )

            if actual_document_text != expected_document_text:
                stats[fmt]["unit_loss"] += 1
                stats[fmt]["order_err"] += 1

        except Exception as e:
            stats[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(
                    f"{fmt} | {os.path.basename(path)} | "
                    f"{type(e).__name__}: {e}"
                )

    # ================================================================
    # PER-FORMAT OUTPUT
    # ================================================================

    for fmt in ["PDF", "PPTX"]:
        s = stats[fmt]
        minimum, average, maximum = token_summary(s["tokens"])
        label = "pages" if fmt == "PDF" else "slides"

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {s['failed']}")
        print(f"Chunks/{label}: {s['chunks']}")
        print(
            f"Min/Avg/Max tokens: "
            f"{minimum} / {average:.1f} / {maximum}"
        )
        print(f"Chunks >400: {s['over_400']}")

    # ================================================================
    # TOTALS
    # ================================================================

    total = {
        key: 0
        for key in new_stats()
        if key != "tokens"
    }

    for fmt in ["PDF", "PPTX"]:
        for key in total:
            total[key] += stats[fmt][key]

    all_tokens = [
        token
        for fmt in ["PDF", "PPTX"]
        for token in stats[fmt]["tokens"]
    ]

    minimum, average, maximum = token_summary(all_tokens)

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['docs']}")
    print(f"Failed: {total['failed']}")
    print(f"Chunks: {total['chunks']}")
    print(
        f"Min/Avg/Max tokens: "
        f"{minimum} / {average:.1f} / {maximum}"
    )
    print()

    print(f"Empty chunks: {total['empty']}")
    print(f"Duplicate IDs: {total['dup_id']}")
    print(f"Index errors: {total['idx_err']}")
    print(f"Method errors: {total['method_err']}")
    print(f"Metadata errors: {total['meta_err']}")
    print(f"Token-count errors: {total['token_err']}")
    print(f"Chunk-ID errors: {total['id_err']}")
    print()

    print(f"Text mismatch errors: {total['text_mismatch']}")
    print(
        f"Chunk-count mismatch errors: "
        f"{total['chunk_count_mismatch']}"
    )
    print(f"Provenance errors: {total['provenance_err']}")
    print(
        f"Unit preservation failures: "
        f"{total['unit_loss']}"
    )
    print(f"Order errors: {total['order_err']}")
    print()

    print(f"Chunks >400: {total['over_400']}")
    print(f"Chunks >512: {total['over_512']}")
    print(f"Chunks >1024: {total['over_1024']}")
    print(f"Chunks >2048: {total['over_2048']}")
    print()

    print(f"Chunks with hierarchy: {total['hier']}")
    print(f"Chunks without hierarchy: {total['no_hier']}")
    print(f"Page-numbered chunks: {total['pages']}")
    print(f"Slide-numbered chunks: {total['slides']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")

        for failure in failures:
            print(f"  - {failure}")

    # ================================================================
    # PASS / FAIL
    # ================================================================

    error_keys = [
        "failed",
        "empty",
        "dup_id",
        "idx_err",
        "method_err",
        "meta_err",
        "token_err",
        "id_err",
        "text_mismatch",
        "chunk_count_mismatch",
        "provenance_err",
        "unit_loss",
        "order_err",
    ]

    critical_errors = sum(
        total[key]
        for key in error_keys
    )

    print(
        "\nPAGE/SLIDE CHUNKING VALIDATION "
        + (
            "PASSED"
            if critical_errors == 0
            else "NEEDS REVIEW"
        )
    )

    print("=" * 72)


if __name__ == "__main__":
    run_tests()