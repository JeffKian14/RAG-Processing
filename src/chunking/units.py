from typing import List
from src.schemas import NormalizedDocument, ChunkUnit
from src.chunking.render import render_block

def build_chunk_units(doc: NormalizedDocument) -> List[ChunkUnit]:
    units = []
    for section in doc.sections:
        for block in section.blocks:
            rendered_text = render_block(block).strip()
            if not rendered_text:
                continue
            units.append(ChunkUnit(
                text=rendered_text,
                block_type=block.block_type,
                section_hierarchy=list(section.hierarchy),
                page_number=getattr(block, "page_number", None),
                slide_number=getattr(block, "slide_number", None)
            ))
    return units