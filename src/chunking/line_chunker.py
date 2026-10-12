from typing import List

from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


def chunk_document(doc: NormalizedDocument, lines_per_chunk: int = 10) -> List[Chunk]:
    if lines_per_chunk <= 0: raise ValueError("lines_per_chunk must be greater than 0")

    line_records = []

    for unit in build_chunk_units(doc):
        for line in unit.text.splitlines():
            if not line.strip(): continue

            line_records.append((
                line,
                unit.section_hierarchy,
                unit.page_number,
                unit.slide_number,
            ))

    chunks = []

    for i in range(0, len(line_records), lines_per_chunk):
        group = line_records[i:i + lines_per_chunk]

        text = "\n".join(record[0] for record in group)
        hierarchies = [record[1] for record in group]
        pages = [record[2] for record in group]
        slides = [record[3] for record in group]

        page = pages[0] if len(set(pages)) == 1 and pages[0] is not None else None
        slide = slides[0] if len(set(slides)) == 1 and slides[0] is not None else None

        chunk_index = len(chunks)

        chunks.append(Chunk(
            chunk_id=generate_chunk_id(doc.document_id, "line", chunk_index, text),
            document_id=doc.document_id,
            chunk_index=chunk_index,
            chunk_method="line",
            text=text,
            enterprise=doc.metadata.enterprise,
            source_filename=doc.metadata.source_filename,
            source_format=doc.metadata.source_format,
            section_hierarchy=longest_common_hierarchy(hierarchies),
            page_number=page,
            slide_number=slide,
            parent_chunk_id=None,
            child_chunk_ids=[],
            token_count=count_tokens(text),
        ))

    return chunks