import os
import glob
import hashlib
from typing import Dict, Callable, List, Tuple

from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized
from src.parsers.markdown_parser import parse_markdown_to_normalized
from src.parsers.pdf_parser import convert_pdf_to_normalized_document
from src.parsers.docx_parser import convert_docx_to_normalized_document
from src.parsers.pptx_parser import convert_pptx_to_normalized_document
from src.chunking.utils import count_tokens, generate_chunk_id


PARSERS: Dict[str, Callable] = {
    ".html": parse_html_to_normalized,
    ".md": parse_markdown_to_normalized,
    ".pdf": convert_pdf_to_normalized_document,
    ".docx": convert_docx_to_normalized_document,
    ".pptx": convert_pptx_to_normalized_document,
}

FORMATS = ["HTML", "MD", "PDF", "DOCX", "PPTX"]


def get_dataset_path() -> str:
    paths = [
        "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets",
        "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets",
    ]

    for path in paths:
        absolute = os.path.abspath(path)
        if os.path.exists(absolute): return absolute

    raise FileNotFoundError("RAG-Multi-Corpus dataset directory not found")


def get_corpus_files() -> List[str]:
    corpus = get_dataset_path()
    files = []

    for ext in PARSERS:
        files.extend(glob.glob(os.path.join(corpus, "**", f"*{ext}"), recursive=True))

    return files


def infer_enterprise(path: str) -> str:
    p = path.lower()

    if "aventro" in p: return "Aventro Motors"
    if "cendara" in p: return "Cendara University"
    if "cloudway" in p: return "CloudWay-24"
    if "velvera" in p: return "Velvera Technologies"
    if "zx bank" in p or "zx_bank" in p or "zx-bank" in p or "zx" in p: return "ZX Bank"

    return "Unknown"


def build_test_metadata(path: str, ext: str) -> Tuple[str, DocumentMetadata]:
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


def parse_source(path: str):
    ext = os.path.splitext(path)[1].lower()

    if ext not in PARSERS:
        raise ValueError(f"Unsupported source format: {ext}")

    if ext in (".html", ".md"):
        document_id, metadata = build_test_metadata(path, ext)
        return PARSERS[ext](path, document_id, metadata)

    return PARSERS[ext](path)


def validate_common_chunk_fields(doc, chunks, expected_method: str, seen_ids: set):
    errors = {
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
    }

    for i, chunk in enumerate(chunks):
        if not chunk.text:
            errors["empty"] += 1

        if chunk.chunk_id in seen_ids:
            errors["dup_id"] += 1

        seen_ids.add(chunk.chunk_id)

        if chunk.chunk_index != i:
            errors["idx_err"] += 1

        if chunk.chunk_method != expected_method:
            errors["method_err"] += 1

        if (
            chunk.document_id != doc.document_id
            or chunk.enterprise != doc.metadata.enterprise
            or chunk.source_filename != doc.metadata.source_filename
            or chunk.source_format != doc.metadata.source_format
        ):
            errors["meta_err"] += 1

        if chunk.token_count != count_tokens(chunk.text):
            errors["token_err"] += 1

        expected_id = generate_chunk_id(doc.document_id, expected_method, i, chunk.text)

        if chunk.chunk_id != expected_id:
            errors["id_err"] += 1

    return errors


def collect_common_chunk_stats(chunks):
    return {
        "chunks": len(chunks),
        "tokens": [chunk.token_count for chunk in chunks],
        "hier": sum(1 for chunk in chunks if chunk.section_hierarchy),
        "no_hier": sum(1 for chunk in chunks if not chunk.section_hierarchy),
        "pages": sum(1 for chunk in chunks if chunk.page_number is not None),
        "slides": sum(1 for chunk in chunks if chunk.slide_number is not None),
    }


def merge_error_counts(target: dict, source: dict):
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def token_summary(tokens: List[int]):
    if not tokens:
        return 0, 0.0, 0

    return min(tokens), sum(tokens) / len(tokens), max(tokens)