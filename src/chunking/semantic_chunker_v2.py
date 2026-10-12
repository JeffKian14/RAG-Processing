import requests
import numpy as np
from typing import List
from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


MIN_TOKENS = 80
TARGET_TOKENS = 220
MAX_TOKENS = 400
BREAKPOINT_PERCENTILE = 85.0
CONTEXT_RADIUS = 1

MODEL_NAME = "text-embedding-nomic-embed-text-v1.5@q8_0"
EMBEDDING_URL = "http://localhost:1234/v1/embeddings"
PREFIX = "clustering: "

_EMB_CACHE = {}
_SESSION = requests.Session()


def _cache_key(text: str, model_name: str, prefix: str) -> str:
    return f"{model_name}\0{prefix}\0{text}"


def _get_embeddings(texts: List[str], model_name: str = MODEL_NAME, embedding_url: str = EMBEDDING_URL, prefix: str = PREFIX, batch_size: int = 32) -> np.ndarray:
    if not texts: return np.empty((0, 0), dtype=np.float32)

    unique_uncached = []

    for text in texts:
        key = _cache_key(text, model_name, prefix)
        if key not in _EMB_CACHE and text not in unique_uncached: unique_uncached.append(text)

    for start in range(0, len(unique_uncached), batch_size):
        batch = unique_uncached[start:start + batch_size]
        inputs = [prefix + text for text in batch]

        try:
            response = _SESSION.post(embedding_url, json={"model": model_name, "input": inputs}, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"LM Studio embedding request failed: {e}") from e

        try:
            payload = response.json()
        except ValueError as e:
            raise RuntimeError("LM Studio returned invalid JSON") from e

        data = payload.get("data")

        if not isinstance(data, list) or len(data) != len(batch):
            raise RuntimeError(f"Expected {len(batch)} embeddings, got {0 if not isinstance(data, list) else len(data)}")

        data = sorted(data, key=lambda item: item.get("index", -1))

        if [item.get("index") for item in data] != list(range(len(batch))):
            raise RuntimeError("LM Studio returned invalid embedding indices")

        for text, item in zip(batch, data):
            vector = np.asarray(item.get("embedding"), dtype=np.float32)

            if vector.ndim != 1 or vector.size == 0:
                raise RuntimeError("LM Studio returned an invalid embedding vector")

            norm = float(np.linalg.norm(vector))

            if not np.isfinite(norm) or norm == 0:
                raise RuntimeError("LM Studio returned a zero or invalid embedding vector")

            _EMB_CACHE[_cache_key(text, model_name, prefix)] = vector / norm

    vectors = [_EMB_CACHE[_cache_key(text, model_name, prefix)] for text in texts]

    if len({vector.shape[0] for vector in vectors}) != 1:
        raise RuntimeError("LM Studio returned inconsistent embedding dimensions")

    return np.stack(vectors).astype(np.float32)


def _char_split_exact(text: str, cap: int) -> List[str]:
    if cap <= 0: raise ValueError("cap must be > 0")
    if not text: return []
    if count_tokens(text) <= cap: return [text]

    fragments = []
    remaining = text

    while remaining:
        if count_tokens(remaining) <= cap:
            fragments.append(remaining)
            break

        low, high, best = 1, len(remaining), 0

        while low <= high:
            mid = (low + high) // 2

            if count_tokens(remaining[:mid]) <= cap:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if best <= 0:
            raise ValueError("Unable to split semantic atom within token cap")

        fragment = remaining[:best]

        if count_tokens(fragment) > cap:
            raise ValueError("Semantic atom splitter produced an oversized fragment")

        fragments.append(fragment)
        remaining = remaining[best:]

    if "".join(fragments) != text:
        raise ValueError("Semantic atom split failed exact preservation")

    return fragments


def _build_atoms(doc: NormalizedDocument, target_tokens: int, max_tokens: int) -> List[dict]:
    units = build_chunk_units(doc)
    atoms = []

    for i, unit in enumerate(units):
        raw = unit.text if i == 0 else "\n\n" + unit.text

        if count_tokens(raw) > max_tokens:
            fragments = _char_split_exact(raw, target_tokens)
        else:
            fragments = [raw]

        for fragment in fragments:
            atoms.append({"raw": fragment, "emb": fragment.strip(), "unit": unit})

    source_text = "\n\n".join(unit.text for unit in units)

    if "".join(atom["raw"] for atom in atoms) != source_text:
        raise ValueError("Semantic atoms failed exact source preservation")

    if any(count_tokens(atom["raw"]) > max_tokens for atom in atoms):
        raise ValueError("Semantic atom exceeds max_tokens")

    return atoms


def _build_context_texts(atoms: List[dict], radius: int) -> List[str]:
    contexts = []

    for i in range(len(atoms)):
        start = max(0, i - radius)
        end = min(len(atoms), i + radius + 1)
        parts = [atoms[j]["emb"] for j in range(start, end) if atoms[j]["emb"]]
        contexts.append("\n\n".join(parts) if parts else " ")

    return contexts


def _semantic_boundaries(atoms: List[dict], percentile: float, radius: int, model_name: str, embedding_url: str) -> tuple:
    if len(atoms) <= 1: return [], []

    contexts = _build_context_texts(atoms, radius)
    embeddings = _get_embeddings(contexts, model_name, embedding_url)

    distances = [1.0 - float(embeddings[i] @ embeddings[i + 1]) for i in range(len(embeddings) - 1)]
    threshold = float(np.percentile(distances, percentile))
    boundaries = [distance > threshold for distance in distances]

    return distances, boundaries


def _group_text(group: List[dict]) -> str:
    return "".join(atom["raw"] for atom in group)


def _group_tokens(group: List[dict]) -> int:
    return count_tokens(_group_text(group))


def _segment_atoms(atoms: List[dict], distances: List[float], boundaries: List[bool], min_tokens: int, target_tokens: int, max_tokens: int) -> List[List[dict]]:
    groups = []
    i = 0

    while i < len(atoms):
        remaining = atoms[i:]

        if _group_tokens(remaining) <= max_tokens:
            groups.append(remaining)
            break

        valid = []
        current_text = ""

        for j in range(i, len(atoms)):
            current_text += atoms[j]["raw"]
            tokens = count_tokens(current_text)

            if tokens > max_tokens: break

            if tokens >= min_tokens:
                semantic_boundary = j < len(atoms) - 1 and boundaries[j]
                distance = distances[j] if j < len(distances) else 0.0
                valid.append((j, tokens, semantic_boundary, distance))

        if valid:
            semantic_candidates = [candidate for candidate in valid if candidate[2]]

            if semantic_candidates:
                best = min(semantic_candidates, key=lambda x: (abs(x[1] - target_tokens), -x[3], -x[1], x[0]))
            else:
                best = min(valid, key=lambda x: (abs(x[1] - target_tokens), -x[1], x[0]))

            end = best[0]
            groups.append(atoms[i:end + 1])
            i = end + 1
            continue

        current_text = ""
        best_j = None

        for j in range(i, len(atoms)):
            candidate = current_text + atoms[j]["raw"]

            if count_tokens(candidate) > max_tokens: break

            current_text = candidate
            best_j = j

        if best_j is None:
            raise ValueError("Unable to construct a chunk under max_tokens")

        groups.append(atoms[i:best_j + 1])
        i = best_j + 1

    return groups


def _repair_tiny_tail(groups: List[List[dict]], min_tokens: int, target_tokens: int, max_tokens: int) -> List[List[dict]]:
    if len(groups) <= 1: return groups

    previous = groups[-2]
    final = groups[-1]
    previous_tokens = _group_tokens(previous)
    final_tokens = _group_tokens(final)

    if final_tokens >= min_tokens: return groups

    if previous_tokens + final_tokens <= max_tokens:
        groups[-2:] = [previous + final]
        return groups

    combined = previous + final
    candidates = []

    for split in range(1, len(combined)):
        left = combined[:split]
        right = combined[split:]
        left_tokens = _group_tokens(left)
        right_tokens = _group_tokens(right)

        if min_tokens <= left_tokens <= max_tokens and min_tokens <= right_tokens <= max_tokens:
            candidates.append((split, left_tokens, right_tokens))

    if not candidates: return groups

    best = min(candidates, key=lambda x: (abs(x[2] - target_tokens), abs(x[1] - target_tokens), -x[2], x[0]))
    split = best[0]
    groups[-2:] = [combined[:split], combined[split:]]

    return groups


def _build_chunk(doc: NormalizedDocument, index: int, group: List[dict]) -> Chunk:
    text = _group_text(group)
    source_units = [atom["unit"] for atom in group]

    hierarchies = [unit.section_hierarchy for unit in source_units]
    pages = [unit.page_number for unit in source_units]
    slides = [unit.slide_number for unit in source_units]

    page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
    slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None

    return Chunk(
        chunk_id=generate_chunk_id(doc.document_id, "semantic_v2", index, text),
        document_id=doc.document_id,
        chunk_index=index,
        chunk_method="semantic_v2",
        text=text,
        enterprise=doc.metadata.enterprise,
        source_filename=doc.metadata.source_filename,
        source_format=doc.metadata.source_format,
        section_hierarchy=longest_common_hierarchy(hierarchies),
        page_number=page,
        slide_number=slide,
        parent_chunk_id=None,
        child_chunk_ids=[],
        token_count=count_tokens(text)
    )


def chunk_document(doc: NormalizedDocument, min_tokens: int = MIN_TOKENS, target_tokens: int = TARGET_TOKENS, max_tokens: int = MAX_TOKENS,
                   breakpoint_percentile: float = BREAKPOINT_PERCENTILE, context_radius: int = CONTEXT_RADIUS,
                   model_name: str = MODEL_NAME, embedding_url: str = EMBEDDING_URL) -> List[Chunk]:

    if not 0 < min_tokens <= target_tokens <= max_tokens:
        raise ValueError("Require 0 < min_tokens <= target_tokens <= max_tokens")

    if not 0 <= breakpoint_percentile <= 100:
        raise ValueError("breakpoint_percentile must be between 0 and 100")

    if context_radius < 0:
        raise ValueError("context_radius must be >= 0")

    units = build_chunk_units(doc)

    if not units: return []

    source_text = "\n\n".join(unit.text for unit in units)
    atoms = _build_atoms(doc, target_tokens, max_tokens)
    distances, boundaries = _semantic_boundaries(atoms, breakpoint_percentile, context_radius, model_name, embedding_url)

    groups = _segment_atoms(atoms, distances, boundaries, min_tokens, target_tokens, max_tokens)
    groups = _repair_tiny_tail(groups, min_tokens, target_tokens, max_tokens)

    chunks = [_build_chunk(doc, i, group) for i, group in enumerate(groups)]

    if "".join(chunk.text for chunk in chunks) != source_text:
        raise ValueError("Semantic V2 failed exact content preservation")

    if any(chunk.token_count > max_tokens for chunk in chunks):
        raise ValueError("Semantic V2 produced an oversized chunk")

    return chunks