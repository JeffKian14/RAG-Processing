import numpy as np
import requests
from typing import List

from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


DEFAULT_MODEL_NAME = "text-embedding-nomic-embed-text-v1.5@q8_0"
DEFAULT_EMBEDDING_URL = "http://localhost:1234/v1/embeddings"
DEFAULT_PREFIX = "clustering: "


def _exact_split(text: str, max_tokens: int) -> List[str]:
    if count_tokens(text) <= max_tokens: return [text]

    parts = []
    remaining = text

    while remaining:
        if count_tokens(remaining) <= max_tokens:
            parts.append(remaining)
            break

        best = 0

        for cut in range(1, len(remaining) + 1):
            if count_tokens(remaining[:cut]) <= max_tokens: best = cut
            else: break

        if best == 0: raise ValueError("Unable to split semantic atom within max_tokens")

        parts.append(remaining[:best])
        remaining = remaining[best:]

    if "".join(parts) != text: raise ValueError("Semantic atom split failed exact preservation")
    return parts


def _embed_texts(texts: List[str], model_name: str, embedding_url: str, batch_size: int = 32) -> np.ndarray:
    vectors = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        inputs = [DEFAULT_PREFIX + (text.strip() or text) for text in batch]

        try:
            response = requests.post(embedding_url, json={"model": model_name, "input": inputs}, timeout=120)
        except requests.RequestException as e:
            raise RuntimeError(f"Cannot connect to LM Studio embedding server: {e}") from e

        if response.status_code != 200:
            raise RuntimeError(f"LM Studio embedding request failed ({response.status_code}): {response.text}")

        payload = response.json()
        data = payload.get("data", [])

        if len(data) != len(batch):
            raise RuntimeError(f"Expected {len(batch)} embeddings but LM Studio returned {len(data)}")

        data = sorted(data, key=lambda item: item["index"])
        vectors.extend(item["embedding"] for item in data)

    embeddings = np.asarray(vectors, dtype=np.float32)

    if embeddings.ndim != 2 or len(embeddings) != len(texts):
        raise RuntimeError("Invalid embedding matrix returned by LM Studio")

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)

    if np.any(norms == 0):
        raise RuntimeError("LM Studio returned a zero-length embedding vector")

    return embeddings / norms


def _build_chunk(doc: NormalizedDocument, chunks: List[Chunk], text: str, source_units: list) -> Chunk:
    pages = [u.page_number for u in source_units]
    slides = [u.slide_number for u in source_units]

    page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
    slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None
    index = len(chunks)

    return Chunk(
        chunk_id=generate_chunk_id(doc.document_id, "semantic", index, text),
        document_id=doc.document_id, chunk_index=index, chunk_method="semantic", text=text,
        enterprise=doc.metadata.enterprise, source_filename=doc.metadata.source_filename,
        source_format=doc.metadata.source_format,
        section_hierarchy=longest_common_hierarchy([u.section_hierarchy for u in source_units]),
        page_number=page, slide_number=slide, parent_chunk_id=None, child_chunk_ids=[],
        token_count=count_tokens(text)
    )


def chunk_document(
    doc: NormalizedDocument,
    max_tokens: int = 400,
    breakpoint_percentile: float = 25.0,
    model_name: str = DEFAULT_MODEL_NAME,
    embedding_url: str = DEFAULT_EMBEDDING_URL
) -> List[Chunk]:

    if max_tokens <= 0: raise ValueError("max_tokens must be > 0")
    if not 0 <= breakpoint_percentile <= 100: raise ValueError("breakpoint_percentile must be between 0 and 100")

    units = build_chunk_units(doc)
    if not units: return []

    source_text = "\n\n".join(u.text for u in units)

    # ----------------------------------------------------------------
    # 1. BUILD SEMANTIC ATOMS
    # ----------------------------------------------------------------

    atoms = []

    for i, unit in enumerate(units):
        raw_text = unit.text if i == 0 else "\n\n" + unit.text

        for fragment in _exact_split(raw_text, max_tokens):
            atoms.append((fragment, unit))

    if "".join(text for text, _ in atoms) != source_text:
        raise ValueError("Semantic atoms failed exact source preservation")

    # ----------------------------------------------------------------
    # 2. EMBED ATOMS + FIND SEMANTIC BOUNDARIES
    # ----------------------------------------------------------------

    boundaries = [False] * max(0, len(atoms) - 1)

    if len(atoms) > 1:
        embeddings = _embed_texts([text for text, _ in atoms], model_name, embedding_url)
        similarities = [float(embeddings[i] @ embeddings[i + 1]) for i in range(len(embeddings) - 1)]
        threshold = float(np.percentile(similarities, breakpoint_percentile))
        boundaries = [similarity < threshold for similarity in similarities]

    # ----------------------------------------------------------------
    # 3. ASSEMBLE FINAL CHUNKS
    # ----------------------------------------------------------------

    chunks = []
    current_text = ""
    current_units = []

    for i, (text, unit) in enumerate(atoms):
        semantic_break = i > 0 and boundaries[i - 1]
        size_break = bool(current_text) and count_tokens(current_text + text) > max_tokens

        if current_text and (semantic_break or size_break):
            chunks.append(_build_chunk(doc, chunks, current_text, current_units))
            current_text, current_units = text, [unit]
        else:
            current_text += text
            current_units.append(unit)

    if current_text:
        chunks.append(_build_chunk(doc, chunks, current_text, current_units))

    # ----------------------------------------------------------------
    # 4. SAFETY CHECKS
    # ----------------------------------------------------------------

    if "".join(chunk.text for chunk in chunks) != source_text:
        raise ValueError("Semantic chunking failed exact content preservation")

    if any(chunk.token_count > max_tokens for chunk in chunks):
        raise ValueError("Semantic chunk exceeded max_tokens")

    return chunks