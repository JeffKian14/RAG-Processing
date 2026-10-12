from typing import List
from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy

def chunk_document(doc: NormalizedDocument) -> List[Chunk]:
    units = build_chunk_units(doc)
    if not units: return []
    
    mode = "page" if any(u.page_number is not None for u in units) else "slide" if any(u.slide_number is not None for u in units) else None
    if not mode: raise ValueError("Page/slide chunking requires page or slide provenance")
    
    groups, curr_id, curr_grp = [], None, []
    for u in units:
        pid = u.page_number if mode == "page" else u.slide_number
        if pid is None: raise ValueError(f"Missing provenance in {mode} mode")
        if curr_id is None: curr_id = pid
        if pid == curr_id: curr_grp.append(u)
        else: groups.append((curr_id, curr_grp)); curr_id, curr_grp = pid, [u]
    if curr_grp: groups.append((curr_id, curr_grp))
        
    chunks = []
    for i, (pid, grp) in enumerate(groups):
        text = "\n\n".join(u.text for u in grp)
        chunks.append(Chunk(
            chunk_id=generate_chunk_id(doc.document_id, "page_slide", i, text),
            document_id=doc.document_id, chunk_index=i, chunk_method="page_slide", text=text,
            enterprise=doc.metadata.enterprise, source_filename=doc.metadata.source_filename,
            source_format=doc.metadata.source_format, section_hierarchy=longest_common_hierarchy([u.section_hierarchy for u in grp]),
            page_number=pid if mode == "page" else None, slide_number=pid if mode == "slide" else None,
            parent_chunk_id=None, child_chunk_ids=[], token_count=count_tokens(text)
        ))
    return chunks