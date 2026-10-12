from typing import List

from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]


def _split_keep_sep(text: str, sep: str) -> List[str]:
    parts = text.split(sep)
    return [parts[i] + sep for i in range(len(parts) - 1)] + ([parts[-1]] if parts[-1] else [])


def _char_split(text: str, max_tokens: int) -> List[str]:
    chunks = []
    remaining = text

    while remaining:
        best = 0

        for cut in range(1, len(remaining) + 1):
            if count_tokens(remaining[:cut]) <= max_tokens: best = cut

        if best == 0: raise ValueError("Unable to split text within max_tokens at character level")

        chunks.append(remaining[:best])
        remaining = remaining[best:]

    return chunks


def _recursive_split(text: str, max_tokens: int, separators: List[str]) -> List[str]:
    if count_tokens(text) <= max_tokens: return [text]
    if not separators: return _char_split(text, max_tokens)

    pieces = _split_keep_sep(text, separators[0])
    if len(pieces) == 1: return _recursive_split(text, max_tokens, separators[1:])

    chunks = []
    current = ""

    for piece in pieces:
        candidate = current + piece

        if count_tokens(candidate) <= max_tokens:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if count_tokens(piece) > max_tokens:
            chunks.extend(_recursive_split(piece, max_tokens, separators[1:]))
        else:
            current = piece

    if current: chunks.append(current)
    return chunks


def chunk_document(doc: NormalizedDocument, max_tokens: int = 400) -> List[Chunk]:
    if max_tokens <= 0: raise ValueError("max_tokens must be > 0")

    units = build_chunk_units(doc)
    if not units: return []

    full_text = ""
    spans = []

    for i, unit in enumerate(units):
        if i > 0: full_text += "\n\n"

        start = len(full_text)
        full_text += unit.text
        spans.append((start, len(full_text), unit))

    raw_chunks = _recursive_split(full_text, max_tokens, SEPARATORS)

    if "".join(raw_chunks) != full_text: raise ValueError("Recursive splitting failed exact content preservation")

    chunks = []
    cursor = 0

    for text in raw_chunks:
        start = cursor
        end = start + len(text)
        cursor = end

        contrib = [unit for s, e, unit in spans if e > start and s < end]

        hierarchies = [unit.section_hierarchy for unit in contrib]
        pages = [unit.page_number for unit in contrib]
        slides = [unit.slide_number for unit in contrib]

        page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
        slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None
        chunk_index = len(chunks)

        chunks.append(Chunk(
            chunk_id=generate_chunk_id(doc.document_id, "recursive", chunk_index, text),
            document_id=doc.document_id, chunk_index=chunk_index, chunk_method="recursive", text=text,
            enterprise=doc.metadata.enterprise, source_filename=doc.metadata.source_filename,
            source_format=doc.metadata.source_format, section_hierarchy=longest_common_hierarchy(hierarchies),
            page_number=page, slide_number=slide, parent_chunk_id=None, child_chunk_ids=[],
            token_count=count_tokens(text)
        ))

    return chunks