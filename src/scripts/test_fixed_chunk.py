import os
import glob
import re
import hashlib
from collections import defaultdict

from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized
from src.parsers.markdown_parser import parse_markdown_to_normalized
from src.parsers.pdf_parser import convert_pdf_to_normalized_document
from src.parsers.docx_parser import convert_docx_to_normalized_document
from src.parsers.pptx_parser import convert_pptx_to_normalized_document
from src.chunking.units import build_chunk_units
from src.chunking.fixed_chunker import chunk_document
from src.chunking.utils import count_tokens, generate_chunk_id


PARSERS = {
    ".html": parse_html_to_normalized,
    ".md": parse_markdown_to_normalized,
    ".pdf": convert_pdf_to_normalized_document,
    ".docx": convert_docx_to_normalized_document,
    ".pptx": convert_pptx_to_normalized_document,
}


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
        "content_loss": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0,
    }


def main():
    print("=" * 72)
    print("PHASE 8B: FIXED-SIZE CHUNKING VALIDATION")
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
            chunks = chunk_document(doc, max_tokens=400)
            stats[fmt]["chunks"] += len(chunks)

            source_text = re.sub(r"\s+", " ", "\n\n".join(unit.text for unit in units)).strip()
            chunk_text = re.sub(r"\s+", " ", "\n\n".join(chunk.text for chunk in chunks)).strip()

            if source_text != chunk_text: stats[fmt]["content_loss"] += 1

            for i, chunk in enumerate(chunks):
                stats[fmt]["tokens"].append(chunk.token_count)

                if chunk.token_count > 400: stats[fmt]["over_400"] += 1
                if not chunk.text.strip(): stats[fmt]["empty"] += 1
                if chunk.chunk_id in seen_ids: stats[fmt]["dup_id"] += 1
                if chunk.chunk_index != i: stats[fmt]["idx_err"] += 1
                if chunk.chunk_method != "fixed": stats[fmt]["method_err"] += 1
                if chunk.token_count != count_tokens(chunk.text): stats[fmt]["token_err"] += 1
                if chunk.chunk_id != generate_chunk_id(doc.document_id, "fixed", i, chunk.text): stats[fmt]["id_err"] += 1

                if chunk.document_id != doc.document_id or chunk.enterprise != doc.metadata.enterprise or chunk.source_filename != doc.metadata.source_filename or chunk.source_format != doc.metadata.source_format:
                    stats[fmt]["meta_err"] += 1

                seen_ids.add(chunk.chunk_id)

                if chunk.section_hierarchy: stats[fmt]["hier"] += 1
                else: stats[fmt]["no_hier"] += 1

                if chunk.page_number is not None: stats[fmt]["pages"] += 1
                if chunk.slide_number is not None: stats[fmt]["slides"] += 1

        except Exception as e:
            stats[fmt]["failed"] += 1
            if len(failures) < 20: failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

    formats = ["HTML", "MD", "PDF", "DOCX", "PPTX"]

    for fmt in formats:
        s = stats[fmt]
        minimum = min(s["tokens"]) if s["tokens"] else 0
        maximum = max(s["tokens"]) if s["tokens"] else 0
        average = sum(s["tokens"]) / len(s["tokens"]) if s["tokens"] else 0

        print(f"\n{fmt}")
        print(f"Documents: {s['docs']}")
        print(f"Failed: {s['failed']}")
        print(f"Chunks: {s['chunks']}")
        print(f"Min/Avg/Max tokens: {minimum} / {average:.1f} / {maximum}")

    total = {key: 0 for key in new_stats() if key != "tokens"}

    for fmt in formats:
        for key in total: total[key] += stats[fmt][key]

    all_tokens = [token for fmt in formats for token in stats[fmt]["tokens"]]

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['docs']}")
    print(f"Failed: {total['failed']}")
    print(f"Chunks: {total['chunks']}")

    if all_tokens:
        print(f"Min/Avg/Max tokens: {min(all_tokens)} / {sum(all_tokens) / len(all_tokens):.1f} / {max(all_tokens)}")

    print(f"Empty chunks: {total['empty']}")
    print(f"Chunks > 400 tokens: {total['over_400']}")
    print(f"Duplicate IDs: {total['dup_id']}")
    print(f"Index errors: {total['idx_err']}")
    print(f"Chunk method errors: {total['method_err']}")
    print(f"Metadata errors: {total['meta_err']}")
    print(f"Token-count errors: {total['token_err']}")
    print(f"Chunk-ID errors: {total['id_err']}")
    print(f"Content preservation failures: {total['content_loss']}")
    print(f"Chunks with hierarchy: {total['hier']}")
    print(f"Chunks without hierarchy: {total['no_hier']}")
    print(f"Page-numbered chunks: {total['pages']}")
    print(f"Slide-numbered chunks: {total['slides']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures: print(f"  - {failure}")

    error_keys = ["failed", "empty", "over_400", "dup_id", "idx_err", "method_err", "meta_err", "token_err", "id_err", "content_loss"]
    errors = sum(total[key] for key in error_keys)

    print("\n" + ("FIXED-SIZE CHUNKING VALIDATION PASSED" if errors == 0 else "FIXED-SIZE CHUNKING VALIDATION NEEDS REVIEW"))
    print("=" * 72)


if __name__ == "__main__": main()