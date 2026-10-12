from typing import List
from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import encode_tokens, decode_tokens, count_tokens, generate_chunk_id, longest_common_hierarchy

def chunk_document(doc: NormalizedDocument, max_tokens: int = 400, overlap_tokens: int = 80) -> List[Chunk]:
    if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens: raise ValueError("Invalid chunking parameters")
    
    stride = max_tokens - overlap_tokens
    units = build_chunk_units(doc)
    
    token_stream, unit_spans = [], []
    sep_tokens = encode_tokens("\n\n")
    
    for i, unit in enumerate(units):
        if i > 0: token_stream.extend(sep_tokens)
        start = len(token_stream)
        token_stream.extend(encode_tokens(unit.text))
        unit_spans.append((start, len(token_stream), unit))
        
    chunks = []
    total_tokens = len(token_stream)
    if total_tokens == 0: return chunks
    
    start = 0
    while start < total_tokens:
        end = min(start + max_tokens, total_tokens)
        text = decode_tokens(token_stream[start:end])
        
        contrib = [u for s, e, u in unit_spans if e > start and s < end]
        c_hiers = [u.section_hierarchy for u in contrib]
        c_pages = [u.page_number for u in contrib]
        c_slides = [u.slide_number for u in contrib]
        
        page = c_pages[0] if len(set(c_pages)) == 1 and c_pages[0] is not None else None
        slide = c_slides[0] if len(set(c_slides)) == 1 and c_slides[0] is not None else None
        
        chunks.append(Chunk(
            chunk_id=generate_chunk_id(doc.document_id, "sliding", len(chunks), text),
            document_id=doc.document_id, chunk_index=len(chunks), chunk_method="sliding", text=text,
            enterprise=doc.metadata.enterprise, source_filename=doc.metadata.source_filename,
            source_format=doc.metadata.source_format, section_hierarchy=longest_common_hierarchy(c_hiers),
            page_number=page, slide_number=slide, parent_chunk_id=None, child_chunk_ids=[],
            token_count=count_tokens(text)
        ))
        
        if end == total_tokens: break
        start += stride
        
    return chunks