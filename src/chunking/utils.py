import hashlib
from typing import List
import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")


# New additive helpers for sliding-window and future chunkers.
# These do NOT change existing fixed-chunker behaviour.
def encode_tokens(text: str) -> List[int]:
    return ENC.encode(text, disallowed_special=())


def decode_tokens(tokens: List[int]) -> str:
    return ENC.decode(tokens)


# LOCKED FROM 8B
def count_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


# LOCKED FROM 8B
def split_text_by_tokens(text: str, max_tokens: int) -> List[str]:
    if max_tokens <= 0: raise ValueError("max_tokens must be > 0")

    text = text.strip()
    if not text: return []
    if count_tokens(text) <= max_tokens: return [text]

    parts = []
    remaining = text

    while count_tokens(remaining) > max_tokens:
        ids = ENC.encode(remaining, disallowed_special=())
        approx = ENC.decode(ids[:max_tokens])

        cut = max(approx.rfind(" "), approx.rfind("\n"), approx.rfind("\t"))

        if cut <= 0:
            cut = min(len(approx), len(remaining))
            while cut > 1 and count_tokens(remaining[:cut]) > max_tokens: cut -= 1

        piece = remaining[:cut].strip()

        if not piece:
            piece = ENC.decode(ids[:max_tokens]).strip()
            remaining = ENC.decode(ids[max_tokens:]).strip()
        else:
            remaining = remaining[cut:].strip()

        if piece: parts.append(piece)

    if remaining.strip(): parts.append(remaining.strip())

    return parts


# LOCKED FROM 8B
def generate_chunk_id(document_id: str, chunk_method: str, chunk_index: int, text: str) -> str:
    raw = f"{document_id}|{chunk_method}|{chunk_index}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# LOCKED FROM 8B
def longest_common_hierarchy(hierarchies: List[List[str]]) -> List[str]:
    if not hierarchies: return []

    common = list(hierarchies[0])

    for hierarchy in hierarchies[1:]:
        i = 0
        while i < len(common) and i < len(hierarchy) and common[i] == hierarchy[i]: i += 1
        common = common[:i]
        if not common: break

    return common