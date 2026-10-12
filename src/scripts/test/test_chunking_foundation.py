import os
import glob
import hashlib
from collections import defaultdict

from src.parsers.html_parser import parse_html_to_normalized
from src.parsers.markdown_parser import parse_markdown_to_normalized
from src.parsers.pdf_parser import convert_pdf_to_normalized_document
from src.parsers.docx_parser import convert_docx_to_normalized_document
from src.parsers.pptx_parser import convert_pptx_to_normalized_document
from src.chunking.units import build_chunk_units
from src.schemas import DocumentMetadata


# ============================================================
# HTML / MARKDOWN ADAPTERS
# ============================================================

def infer_enterprise(path):
    p = path.lower()

    if "aventro" in p: return "Aventro Motors"
    if "cendara" in p: return "Cendara University"
    if "cloudway" in p: return "CloudWay-24"
    if "velvera" in p: return "Velvera Technologies"
    if "zx bank" in p or "zx_bank" in p or "zx-bank" in p or "zx" in p: return "ZX Bank"

    return "Unknown"


def build_metadata(path, source_format):
    return DocumentMetadata(
        enterprise=infer_enterprise(path),
        source_filename=os.path.basename(path),
        source_format=source_format,
        document_version=None,
        author=None,
        date=None,
        access_groups=[],
    )


def build_document_id(path, enterprise):
    identity = enterprise + "::" + os.path.basename(path)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def parse_html_file(path):
    metadata = build_metadata(path, "html")
    document_id = build_document_id(path, metadata.enterprise)
    return parse_html_to_normalized(path, document_id, metadata)


def parse_markdown_file(path):
    metadata = build_metadata(path, "md")
    document_id = build_document_id(path, metadata.enterprise)
    return parse_markdown_to_normalized(path, document_id, metadata)


# ============================================================
# PARSER REGISTRY
# ============================================================

PARSERS = {
    ".html": parse_html_file,
    ".md": parse_markdown_file,
    ".pdf": convert_pdf_to_normalized_document,
    ".docx": convert_docx_to_normalized_document,
    ".pptx": convert_pptx_to_normalized_document,
}


# ============================================================
# STATS
# ============================================================

def new_stats():
    return {
        "documents": 0,
        "success": 0,
        "failed": 0,
        "units": 0,
        "text": 0,
        "list": 0,
        "table": 0,
        "image": 0,
        "empty_units": 0,
        "missing_hierarchy": 0,
        "page_units": 0,
        "slide_units": 0,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 72)
    print("PHASE 8A: CHUNKING FOUNDATION VALIDATION")
    print("=" * 72)

    corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus): corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")

    stats = defaultdict(new_stats)
    failures = []

    for ext, parser in PARSERS.items():
        files = glob.glob(os.path.join(corpus, "**", f"*{ext}"), recursive=True)
        fmt = ext[1:].upper()

        for path in files:
            stats[fmt]["documents"] += 1

            try:
                doc = parser(path)
                units = build_chunk_units(doc)

                stats[fmt]["success"] += 1
                stats[fmt]["units"] += len(units)

                for unit in units:
                    if not unit.text.strip(): stats[fmt]["empty_units"] += 1
                    if not unit.section_hierarchy: stats[fmt]["missing_hierarchy"] += 1
                    if unit.page_number is not None: stats[fmt]["page_units"] += 1
                    if unit.slide_number is not None: stats[fmt]["slide_units"] += 1

                    if unit.block_type in ("text", "list", "table", "image"): stats[fmt][unit.block_type] += 1
                    else: raise ValueError(f"Invalid block_type: {unit.block_type}")

            except Exception as e:
                stats[fmt]["failed"] += 1
                if len(failures) < 20: failures.append(f"{fmt} | {os.path.basename(path)} | {type(e).__name__}: {e}")

    formats = ["HTML", "MD", "PDF", "DOCX", "PPTX"]

    for fmt in formats:
        s = stats[fmt]

        print(f"\n{fmt}")
        print(f"Documents: {s['documents']}")
        print(f"Successfully processed: {s['success']}")
        print(f"Failed: {s['failed']}")
        print(f"Units: {s['units']}")
        print(f"Text: {s['text']}")
        print(f"List: {s['list']}")
        print(f"Table: {s['table']}")
        print(f"Image: {s['image']}")
        print(f"Page-numbered units: {s['page_units']}")
        print(f"Slide-numbered units: {s['slide_units']}")
        print(f"Units with empty hierarchy: {s['missing_hierarchy']}")
        print(f"Empty units: {s['empty_units']}")

    total = new_stats()

    for fmt in formats:
        for key in total: total[key] += stats[fmt][key]

    print("\n" + "-" * 72)
    print("TOTAL")
    print(f"Documents: {total['documents']}")
    print(f"Successfully processed: {total['success']}")
    print(f"Failed: {total['failed']}")
    print(f"Units: {total['units']}")
    print(f"Text: {total['text']}")
    print(f"List: {total['list']}")
    print(f"Table: {total['table']}")
    print(f"Image: {total['image']}")
    print(f"Page-numbered units: {total['page_units']}")
    print(f"Slide-numbered units: {total['slide_units']}")
    print(f"Units with empty hierarchy: {total['missing_hierarchy']}")
    print(f"Empty units: {total['empty_units']}")
    print("-" * 72)

    if failures:
        print("\nFirst failures:")
        for failure in failures: print(f"  - {failure}")

    serious_errors = total["failed"] > 0 or total["empty_units"] > 0

    print("\n" + ("CHUNKING FOUNDATION VALIDATION PASSED" if not serious_errors else "CHUNKING FOUNDATION VALIDATION NEEDS REVIEW"))
    print("=" * 72)


if __name__ == "__main__": main()