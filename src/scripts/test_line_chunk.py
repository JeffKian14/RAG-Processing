import os
from collections import defaultdict

from src.chunking.units import build_chunk_units
from src.chunking.line_chunker import chunk_document
from src.chunking.chunk_test_utils import (
    FORMATS,
    get_corpus_files,
    parse_source,
    validate_common_chunk_fields,
    collect_common_chunk_stats,
    merge_error_counts,
    token_summary,
)


LINES_PER_CHUNK = 10


def new_stats():
    return {
        "docs": 0,
        "failed": 0,
        "chunks": 0,
        "src_lines": 0,
        "tokens": [],
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
        "txt_miss": 0,
        "cnt_miss": 0,
        "line_loss": 0,
        "line_cnt_err": 0,
        "over_400": 0,
        "over_512": 0,
        "over_1024": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0,
    }


def main():
    print("=" * 72)
    print("PHASE 8D: LINE CHUNKING VALIDATION")
    print("=" * 72)

    stats = defaultdict(new_stats)
    failures = []
    seen_ids = set()

    for path in get_corpus_files():
        ext = os.path.splitext(path)[1].lower()
        fmt = ext[1:].upper()
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path)
            units = build_chunk_units(doc)

            # ------------------------------------------------------------
            # Build expected source lines independently
            # ------------------------------------------------------------

            expected_lines = []

            for unit in units:
                for line in unit.text.splitlines():
                    if line.strip():
                        expected_lines.append(line)

            stats[fmt]["src_lines"] += len(expected_lines)

            # ------------------------------------------------------------
            # Build expected 10-line groups
            # ------------------------------------------------------------

            expected_chunks = [
                "\n".join(expected_lines[i:i + LINES_PER_CHUNK])
                for i in range(0, len(expected_lines), LINES_PER_CHUNK)
            ]

            # ------------------------------------------------------------
            # Run actual line chunker
            # ------------------------------------------------------------

            chunks = chunk_document(doc, lines_per_chunk=LINES_PER_CHUNK)

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
            # Common Chunk-field validation
            # ------------------------------------------------------------

            common_errors = validate_common_chunk_fields(doc, chunks, "line", seen_ids)
            merge_error_counts(stats[fmt], common_errors)

            # ------------------------------------------------------------
            # Expected number of chunks
            # ------------------------------------------------------------

            if len(chunks) != len(expected_chunks):
                stats[fmt]["cnt_miss"] += 1

            actual_lines = []

            # ------------------------------------------------------------
            # Line-specific validation
            # ------------------------------------------------------------

            for i, chunk in enumerate(chunks):
                lines = chunk.text.splitlines()
                actual_lines.extend(lines)

                if i < len(expected_chunks) and chunk.text != expected_chunks[i]:
                    stats[fmt]["txt_miss"] += 1

                if i < len(chunks) - 1 and len(lines) != LINES_PER_CHUNK:
                    stats[fmt]["line_cnt_err"] += 1

                if i == len(chunks) - 1 and not (1 <= len(lines) <= LINES_PER_CHUNK):
                    stats[fmt]["line_cnt_err"] += 1

                # Informational only
                if chunk.token_count > 400: stats[fmt]["over_400"] += 1
                if chunk.token_count > 512: stats[fmt]["over_512"] += 1
                if chunk.token_count > 1024: stats[fmt]["over_1024"] += 1

            # ------------------------------------------------------------
            # No line loss / duplication / reordering
            # ------------------------------------------------------------

            if actual_lines != expected_lines:
                stats[fmt]["line_loss"] += 1

        except Exception as e:
            stats[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

    # ================================================================
    # PER-FORMAT SUMMARY
    # ================================================================

    for fmt in FORMATS:
        s = stats[fmt]
        minimum, average, maximum = token_summary(s["tokens"])
        avg_lines = s["src_lines"] / s["chunks"] if s["chunks"] else 0

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {s['failed']}")
        print(f"Source lines: {s['src_lines']}")
        print(f"Chunks: {s['chunks']}")
        print(f"Avg lines/chunk: {avg_lines:.2f}")
        print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
        print(f"Chunks >400: {s['over_400']}")

    # ================================================================
    # TOTAL SUMMARY
    # ================================================================

    total = {key: 0 for key in new_stats() if key != "tokens"}

    for fmt in FORMATS:
        for key in total:
            total[key] += stats[fmt][key]

    all_tokens = [token for fmt in FORMATS for token in stats[fmt]["tokens"]]
    minimum, average, maximum = token_summary(all_tokens)

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['docs']}")
    print(f"Failed: {total['failed']}")
    print(f"Source lines: {total['src_lines']}")
    print(f"Chunks: {total['chunks']}")
    print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
    print(f"Empty chunks: {total['empty']}")
    print(f"Duplicate IDs: {total['dup_id']}")
    print(f"Index errors: {total['idx_err']}")
    print(f"Method errors: {total['method_err']}")
    print(f"Metadata errors: {total['meta_err']}")
    print(f"Token-count errors: {total['token_err']}")
    print(f"Chunk-ID errors: {total['id_err']}")
    print(f"Chunk text mismatch errors: {total['txt_miss']}")
    print(f"Chunk count mismatch errors: {total['cnt_miss']}")
    print(f"Line preservation failures: {total['line_loss']}")
    print(f"Line-count errors: {total['line_cnt_err']}")
    print(f"Chunks >400: {total['over_400']}")
    print(f"Chunks >512: {total['over_512']}")
    print(f"Chunks >1024: {total['over_1024']}")
    print(f"Chunks with hierarchy: {total['hier']}")
    print(f"Chunks without hierarchy: {total['no_hier']}")
    print(f"Page-numbered chunks: {total['pages']}")
    print(f"Slide-numbered chunks: {total['slides']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures:
            print(f"  - {failure}")

    # Oversized chunks are intentionally NOT treated as failures.
    error_keys = [
        "failed",
        "empty",
        "dup_id",
        "idx_err",
        "method_err",
        "meta_err",
        "token_err",
        "id_err",
        "txt_miss",
        "cnt_miss",
        "line_loss",
        "line_cnt_err",
    ]

    errors = sum(total[key] for key in error_keys)

    print("\n" + ("LINE CHUNKING VALIDATION PASSED" if errors == 0 else "LINE CHUNKING VALIDATION NEEDS REVIEW"))
    print("=" * 72)


if __name__ == "__main__":
    main()