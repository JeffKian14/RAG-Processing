from typing import List

from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, split_text_by_tokens, generate_chunk_id, longest_common_hierarchy


def chunk_document(doc: NormalizedDocument, max_tokens: int = 400) -> List[Chunk]:
    if max_tokens <= 0: raise ValueError("max_tokens must be > 0")

    units = build_chunk_units(doc)
    chunks = []

    current_texts = []
    current_hierarchies = []
    current_pages = []
    current_slides = []

    def flush():
        if not current_texts: return

        text = "\n\n".join(current_texts)
        page = current_pages[0] if len(set(current_pages)) == 1 and current_pages[0] is not None else None
        slide = current_slides[0] if len(set(current_slides)) == 1 and current_slides[0] is not None else None
        index = len(chunks)

        chunks.append(Chunk(
            chunk_id=generate_chunk_id(doc.document_id, "fixed", index, text),
            document_id=doc.document_id,
            chunk_index=index,
            chunk_method="fixed",
            text=text,
            enterprise=doc.metadata.enterprise,
            source_filename=doc.metadata.source_filename,
            source_format=doc.metadata.source_format,
            section_hierarchy=longest_common_hierarchy(current_hierarchies),
            page_number=page,
            slide_number=slide,
            parent_chunk_id=None,
            child_chunk_ids=[],
            token_count=count_tokens(text),
        ))

        current_texts.clear()
        current_hierarchies.clear()
        current_pages.clear()
        current_slides.clear()

    for unit in units:
        fragments = split_text_by_tokens(unit.text, max_tokens) if count_tokens(unit.text) > max_tokens else [unit.text]

        for fragment in fragments:
            candidate = "\n\n".join(current_texts + [fragment])

            if current_texts and count_tokens(candidate) > max_tokens: flush()

            current_texts.append(fragment)
            current_hierarchies.append(unit.section_hierarchy)
            current_pages.append(unit.page_number)
            current_slides.append(unit.slide_number)

    flush()
    return chunks