import os
import glob
import hashlib
from collections import defaultdict

from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized
from src.parsers.markdown_parser import parse_markdown_to_normalized
from src.parsers.pdf_parser import convert_pdf_to_normalized_document
from src.parsers.docx_parser import convert_docx_to_normalized_document
from src.parsers.pptx_parser import convert_pptx_to_normalized_document

from src.chunking.units import build_chunk_units
from src.chunking.sliding_chunker import chunk_document
from src.chunking.utils import encode_tokens, decode_tokens, count_tokens, generate_chunk_id


PARSERS = {
    ".html": parse_html_to_normalized,
    ".md": parse_markdown_to_normalized,
    ".pdf": convert_pdf_to_normalized_document,
    ".docx": convert_docx_to_normalized_document,
    ".pptx": convert_pptx_to_normalized_document,
}


MAX_TOKENS = 400
OVERLAP_TOKENS = 80
STRIDE = MAX_TOKENS - OVERLAP_TOKENS


def infer_enterprise(path):
    p = path.lower()

    if "aventro" in p: return "Aventro Motors"
    if "cendara" in p: return "Cendara University"
    if "cloudway" in p: return "CloudWay-24"
    if "velvera" in p: return "Velvera Technologies"
    if "zx bank" in p or "zx_bank" in p or "zx-bank" in p or "zx" in p: return "ZX Bank"

    return "Unknown"


def get_base_meta(path, ext):
    enterprise = infer_enterprise(path)
    document_id = hashlib.sha256(f"{enterprise}::{os.path.basename(path)}".encode("utf-8")).hexdigest()

    metadata = DocumentMetadata(
        enterprise=enterprise,
        source_filename=os.path.basename(path),
        source_format=ext[1:],
        document_version=None,
        author=None,
        date=None,
        access_groups=[],
    )

    return document_id, metadata


def parse_source(path, ext):
    if ext in (".html", ".md"):
        document_id, metadata = get_base_meta(path, ext)
        return PARSERS[ext](path, document_id, metadata)

    return PARSERS[ext](path)


def new_stats():
    return {
        "docs": 0,
        "failed": 0,
        "chunks": 0,
        "tokens": [],
        "over_400": 0,
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
        "window_err": 0,
        "count_err": 0,
        "overlap_err": 0,
        "coverage_err": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0,
    }


def build_expected_stream(units):
    stream = []
    separator = encode_tokens("\n\n")

    for i, unit in enumerate(units):
        if i > 0: stream.extend(separator)
        stream.extend(encode_tokens(unit.text))

    return stream


def build_expected_windows(total_tokens):
    windows = []
    if total_tokens == 0: return windows

    start = 0

    while start < total_tokens:
        end = min(start + MAX_TOKENS, total_tokens)
        windows.append((start, end))

        if end == total_tokens: break

        start += STRIDE

    return windows


def main():
    print("=" * 72)
    print("PHASE 8C: SLIDING-WINDOW CHUNKING VALIDATION")
    print("=" * 72)

    corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus): corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")

    stats = defaultdict(new_stats)
    failures = []
    seen_ids = set()

    files = []
    for ext in PARSERS: files.extend(glob.glob(os.path.join(corpus, "**", f"*{ext}"), recursive=True))

    for path in files:
        ext = os.path.splitext(path)[1].lower()
        fmt = ext[1:].upper()
        stats[fmt]["docs"] += 1

        try:
            doc = parse_source(path, ext)
            units = build_chunk_units(doc)
            chunks = chunk_document(doc, max_tokens=MAX_TOKENS, overlap_tokens=OVERLAP_TOKENS)

            stats[fmt]["chunks"] += len(chunks)

            # ------------------------------------------------------------
            # Reconstruct exact expected token stream
            # ------------------------------------------------------------

            token_stream = build_expected_stream(units)
            expected_windows = build_expected_windows(len(token_stream))

            # ------------------------------------------------------------
            # Chunk count validation
            # ------------------------------------------------------------

            if len(chunks) != len(expected_windows):
                stats[fmt]["count_err"] += 1

            # ------------------------------------------------------------
            # Coverage validation
            # First chunk must start at 0.
            # Last expected window must reach EOF.
            # Consecutive windows must advance by STRIDE.
            # ------------------------------------------------------------

            if expected_windows:
                if expected_windows[0][0] != 0: stats[fmt]["coverage_err"] += 1
                if expected_windows[-1][1] != len(token_stream): stats[fmt]["coverage_err"] += 1

                for i in range(1, len(expected_windows)):
                    if expected_windows[i][0] - expected_windows[i - 1][0] != STRIDE:
                        stats[fmt]["coverage_err"] += 1

            # ------------------------------------------------------------
            # Exact overlap validation
            # ------------------------------------------------------------

            for i in range(len(expected_windows) - 1):
                current_start, current_end = expected_windows[i]
                next_start, next_end = expected_windows[i + 1]

                actual_overlap = max(0, min(current_end, next_end) - max(current_start, next_start))

                if actual_overlap != OVERLAP_TOKENS:
                    stats[fmt]["overlap_err"] += 1

            # ------------------------------------------------------------
            # Chunk validation
            # ------------------------------------------------------------

            for i, chunk in enumerate(chunks):
                stats[fmt]["tokens"].append(chunk.token_count)

                if not chunk.text:
                    stats[fmt]["empty"] += 1

                if chunk.token_count > MAX_TOKENS:
                    stats[fmt]["over_400"] += 1

                if chunk.chunk_id in seen_ids:
                    stats[fmt]["dup_id"] += 1

                seen_ids.add(chunk.chunk_id)

                if chunk.chunk_index != i:
                    stats[fmt]["idx_err"] += 1

                if chunk.chunk_method != "sliding":
                    stats[fmt]["method_err"] += 1

                if (
                    chunk.document_id != doc.document_id
                    or chunk.enterprise != doc.metadata.enterprise
                    or chunk.source_filename != doc.metadata.source_filename
                    or chunk.source_format != doc.metadata.source_format
                ):
                    stats[fmt]["meta_err"] += 1

                if chunk.token_count != count_tokens(chunk.text):
                    stats[fmt]["token_err"] += 1

                expected_id = generate_chunk_id(doc.document_id, "sliding", i, chunk.text)

                if chunk.chunk_id != expected_id:
                    stats[fmt]["id_err"] += 1

                # Exact expected window validation
                if i < len(expected_windows):
                    start, end = expected_windows[i]
                    expected_text = decode_tokens(token_stream[start:end])

                    if chunk.text != expected_text:
                        stats[fmt]["window_err"] += 1

                if chunk.section_hierarchy:
                    stats[fmt]["hier"] += 1
                else:
                    stats[fmt]["no_hier"] += 1

                if chunk.page_number is not None:
                    stats[fmt]["pages"] += 1

                if chunk.slide_number is not None:
                    stats[fmt]["slides"] += 1

        except Exception as e:
            stats[fmt]["failed"] += 1

            if len(failures) < 20:
                failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

    formats = ["HTML", "MD", "PDF", "DOCX", "PPTX"]

    # ============================================================
    # PER-FORMAT SUMMARY
    # ============================================================

    for fmt in formats:
        s = stats[fmt]

        minimum = min(s["tokens"]) if s["tokens"] else 0
        maximum = max(s["tokens"]) if s["tokens"] else 0
        average = sum(s["tokens"]) / len(s["tokens"]) if s["tokens"] else 0
        avg_chunks = s["chunks"] / s["docs"] if s["docs"] else 0

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {s['failed']}")
        print(f"Chunks: {s['chunks']}")
        print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")
        print(f"Avg chunks/document: {avg_chunks:.2f}")

    # ============================================================
    # TOTAL SUMMARY
    # ============================================================

    total = {key: 0 for key in new_stats() if key != "tokens"}

    for fmt in formats:
        for key in total:
            total[key] += stats[fmt][key]

    all_tokens = [token for fmt in formats for token in stats[fmt]["tokens"]]

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['docs']}")
    print(f"Failed: {total['failed']}")
    print(f"Chunks: {total['chunks']}")

    if all_tokens:
        print(f"Min/Avg/Max tokens: {min(all_tokens)} / {sum(all_tokens) / len(all_tokens):.1f} / {max(all_tokens)}")

    print(f"Empty chunks: {total['empty']}")
    print(f"Chunks > {MAX_TOKENS} tokens: {total['over_400']}")
    print(f"Duplicate IDs: {total['dup_id']}")
    print(f"Index errors: {total['idx_err']}")
    print(f"Chunk method errors: {total['method_err']}")
    print(f"Metadata errors: {total['meta_err']}")
    print(f"Token-count errors: {total['token_err']}")
    print(f"Chunk-ID errors: {total['id_err']}")
    print(f"Window mismatch errors: {total['window_err']}")
    print(f"Chunk-count mismatch errors: {total['count_err']}")
    print(f"Overlap errors: {total['overlap_err']}")
    print(f"Coverage/stride errors: {total['coverage_err']}")
    print(f"Chunks with hierarchy: {total['hier']}")
    print(f"Chunks without hierarchy: {total['no_hier']}")
    print(f"Page-numbered chunks: {total['pages']}")
    print(f"Slide-numbered chunks: {total['slides']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures:
            print(f"  - {failure}")

    error_keys = [
        "failed",
        "empty",
        "over_400",
        "dup_id",
        "idx_err",
        "method_err",
        "meta_err",
        "token_err",
        "id_err",
        "window_err",
        "count_err",
        "overlap_err",
        "coverage_err",
    ]

    errors = sum(total[key] for key in error_keys)

    print("\n" + ("SLIDING-WINDOW CHUNKING VALIDATION PASSED" if errors == 0 else "SLIDING-WINDOW CHUNKING VALIDATION NEEDS REVIEW"))
    print("=" * 72)


if __name__ == "__main__":
    main()