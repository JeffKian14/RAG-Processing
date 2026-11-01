"""Build structure-aware parents and linked retrieval children.

Parents respect changes in the top-level heading. Children partition each
parent without overlap; concatenating either level reconstructs the rendered
ChunkUnit source exactly, including its inter-unit separators.
"""

from typing import List, Tuple
from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


PARENT_TARGET_TOKENS = 800
PARENT_MAX_TOKENS = 1000

CHILD_TARGET_TOKENS = 220
CHILD_MAX_TOKENS = 300

SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]


def _split_keep_sep(text: str, sep: str) -> List[str]:
    if not sep: return [text]
    parts = text.split(sep)
    result = [parts[i] + sep for i in range(len(parts) - 1)]
    if parts[-1]: result.append(parts[-1])
    return result


def _char_split_exact(text: str, max_tokens: int) -> List[str]:
    if count_tokens(text) <= max_tokens: return [text]

    parts, remaining = [], text

    while remaining:
        if count_tokens(remaining) <= max_tokens:
            parts.append(remaining)
            break

        low, high, best = 1, len(remaining), 0

        while low <= high:
            mid = (low + high) // 2

            if count_tokens(remaining[:mid]) <= max_tokens:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if best <= 0: raise ValueError("Unable to split oversized text")

        parts.append(remaining[:best])
        remaining = remaining[best:]

    if "".join(parts) != text: raise ValueError("Character split failed exact preservation")
    if any(count_tokens(part) > max_tokens for part in parts): raise ValueError("Character split produced oversized fragment")

    return parts


def _recursive_split(text: str, max_tokens: int, separators: List[str]) -> List[str]:
    if count_tokens(text) <= max_tokens: return [text]
    if not separators: return _char_split_exact(text, max_tokens)

    sep = separators[0]
    pieces = _split_keep_sep(text, sep)

    if len(pieces) == 1:
        return _recursive_split(text, max_tokens, separators[1:])

    output, current = [], ""

    for piece in pieces:
        candidate = current + piece

        if count_tokens(candidate) <= max_tokens:
            current = candidate
            continue

        if current:
            output.append(current)
            current = ""

        if count_tokens(piece) > max_tokens:
            output.extend(_recursive_split(piece, max_tokens, separators[1:]))
        else:
            current = piece

    if current: output.append(current)

    if "".join(output) != text: raise ValueError("Recursive split failed exact preservation")
    if any(count_tokens(part) > max_tokens for part in output): raise ValueError("Recursive split produced oversized fragment")

    return output


def _build_atoms(doc: NormalizedDocument) -> List[dict]:
    """
    Build exact source atoms.

    IMPORTANT:
    Split unit.text BEFORE adding the inter-unit "\\n\\n" separator,
    and include that separator in the first fragment's token budget.
    This prevents oversized atoms and separator-only fragments from
    inheriting the next unit's provenance.
    """
    units = build_chunk_units(doc)
    atoms = []

    for unit_index, unit in enumerate(units):
        prefix = "\n\n" if unit_index > 0 else ""

        if count_tokens(prefix + unit.text) <= CHILD_MAX_TOKENS:
            fragments = [unit.text]
        else:
            # Leave space for the separator without making it a separate
            # atom. Recount the actual concatenation rather than assuming
            # token counts are additive at a string boundary.
            limit = CHILD_MAX_TOKENS - count_tokens(prefix)
            while limit > 0:
                fragments = _recursive_split(unit.text, limit, SEPARATORS)
                if count_tokens(prefix + fragments[0]) <= CHILD_MAX_TOKENS:
                    break
                limit -= 1
            else:
                raise ValueError("Unable to fit a source unit with its separator")

        for fragment_index, fragment in enumerate(fragments):
            raw = prefix + fragment if fragment_index == 0 else fragment
            atoms.append({"raw": raw, "unit": unit})

    source_text = "\n\n".join(unit.text for unit in units)

    if "".join(atom["raw"] for atom in atoms) != source_text:
        raise ValueError("Hierarchical atoms failed exact source preservation")

    if any(count_tokens(atom["raw"]) > CHILD_MAX_TOKENS for atom in atoms):
        raise ValueError("Hierarchical atom exceeds child maximum")

    return atoms


def _topic_key(atom: dict):
    """
    Parent structural compatibility.

    Different subheadings sharing the same top-level heading may
    belong to the same parent.

    Examples:
    ["Warranty & Service", "Coverage"]
    ["Warranty & Service", "Repair"]
        -> same topic key

    Empty hierarchy uses None.
    """
    hierarchy = atom["unit"].section_hierarchy
    return hierarchy[0] if hierarchy else None


def _build_topic_groups(atoms: List[dict]) -> List[List[dict]]:
    if not atoms: return []

    groups = []
    current = [atoms[0]]
    current_key = _topic_key(atoms[0])

    for atom in atoms[1:]:
        key = _topic_key(atom)

        if key == current_key:
            current.append(atom)
        else:
            groups.append(current)
            current = [atom]
            current_key = key

    if current: groups.append(current)

    return groups


def _group_text(group: List[dict]) -> str:
    return "".join(atom["raw"] for atom in group)


def _group_tokens(group: List[dict]) -> int:
    return count_tokens(_group_text(group))


def _split_by_target(atoms: List[dict], target_tokens: int, max_tokens: int) -> List[List[dict]]:
    """
    Dynamic-programming partitioning.

    Objective:
    - no segment > max_tokens
    - prefer segment sizes near target_tokens
    - avoid tiny trailing segments produced by greedy splitting

    If the complete input already fits max_tokens, keep it intact.
    """
    if not atoms: return []
    if _group_tokens(atoms) <= max_tokens: return [atoms]

    n = len(atoms)

    # dp[i] = (cost, number_of_chunks, split_indices)
    dp = [None] * (n + 1)
    dp[n] = (0.0, 0, [])

    for i in range(n - 1, -1, -1):
        text = ""

        for j in range(i, n):
            text += atoms[j]["raw"]
            tokens = count_tokens(text)

            if tokens > max_tokens: break
            if dp[j + 1] is None: continue

            # Squared distance heavily penalizes very small/large pieces.
            segment_cost = float((tokens - target_tokens) ** 2)
            future_cost, future_chunks, future_splits = dp[j + 1]

            candidate = (
                segment_cost + future_cost,
                1 + future_chunks,
                [j + 1] + future_splits
            )

            if dp[i] is None:
                dp[i] = candidate
                continue

            current_cost, current_chunks, current_splits = dp[i]

            # Lower cost wins.
            # Tie -> fewer chunks.
            # Final tie -> deterministic lexicographic split order.
            if candidate[0] < current_cost:
                dp[i] = candidate
            elif candidate[0] == current_cost and candidate[1] < current_chunks:
                dp[i] = candidate
            elif candidate[0] == current_cost and candidate[1] == current_chunks and candidate[2] < current_splits:
                dp[i] = candidate

    if dp[0] is None:
        raise ValueError("Unable to partition atoms under max_tokens")

    splits = dp[0][2]
    groups = []
    start = 0

    for end in splits:
        groups.append(atoms[start:end])
        start = end

    if start != n:
        raise ValueError("Target segmentation did not consume every atom")

    if "".join(_group_text(group) for group in groups) != _group_text(atoms):
        raise ValueError("Target segmentation failed exact preservation")

    if any(_group_tokens(group) > max_tokens for group in groups):
        raise ValueError("Target segmentation exceeded max_tokens")

    return groups


def _metadata_from_group(group: List[dict]):
    units = [atom["unit"] for atom in group]

    hierarchies = [unit.section_hierarchy for unit in units]
    pages = [unit.page_number for unit in units]
    slides = [unit.slide_number for unit in units]

    hierarchy = longest_common_hierarchy(hierarchies)
    page = pages[0] if pages and len(set(pages)) == 1 and pages[0] is not None else None
    slide = slides[0] if slides and len(set(slides)) == 1 and slides[0] is not None else None

    return hierarchy, page, slide


def chunk_document(doc: NormalizedDocument) -> Tuple[List[Chunk], List[Chunk]]:
    """Return ``(parents, children)`` with deterministic IDs and links.

    Parent target/max: 800/1000 tokens. Child target/max: 220/300 tokens.
    Complete topics or parents already under their maximum stay intact.
    A chunk spanning multiple pages or slides uses None for that scalar
    provenance field; its hierarchy is the common prefix of its units.
    Oversized blocks split at paragraphs/lines before finer boundaries.
    """
    atoms = _build_atoms(doc)

    if not atoms: return [], []

    source_text = _group_text(atoms)

    # ================================================================
    # STAGE 1 — PARENT TOPIC GROUPS
    # ================================================================

    topic_groups = _build_topic_groups(atoms)
    parent_groups = []

    for topic_group in topic_groups:
        if _group_tokens(topic_group) <= PARENT_MAX_TOKENS:
            # Never force a complete topic to 800 tokens.
            parent_groups.append(topic_group)
        else:
            parent_groups.extend(_split_by_target(topic_group, PARENT_TARGET_TOKENS, PARENT_MAX_TOKENS))

    if "".join(_group_text(group) for group in parent_groups) != source_text:
        raise ValueError("Parent grouping failed source preservation")

    # ================================================================
    # STAGE 2 — CHILDREN WITHIN EACH PARENT
    # ================================================================

    parents = []
    children = []

    for parent_index, parent_group in enumerate(parent_groups):
        parent_text = _group_text(parent_group)
        parent_id = generate_chunk_id(doc.document_id, "hierarchical_parent", parent_index, parent_text)

        child_groups = _split_by_target(parent_group, CHILD_TARGET_TOKENS, CHILD_MAX_TOKENS)

        if "".join(_group_text(group) for group in child_groups) != parent_text:
            raise ValueError("Children failed to reconstruct parent")

        child_ids = []

        for child_group in child_groups:
            child_index = len(children)
            child_text = _group_text(child_group)
            hierarchy, page, slide = _metadata_from_group(child_group)

            child_id = generate_chunk_id(doc.document_id, "hierarchical_child", child_index, child_text)
            child_ids.append(child_id)

            children.append(
                Chunk(
                    chunk_id=child_id,
                    document_id=doc.document_id,
                    chunk_index=child_index,
                    chunk_method="hierarchical_child",
                    text=child_text,
                    enterprise=doc.metadata.enterprise,
                    source_filename=doc.metadata.source_filename,
                    source_format=doc.metadata.source_format,
                    section_hierarchy=hierarchy,
                    page_number=page,
                    slide_number=slide,
                    parent_chunk_id=parent_id,
                    child_chunk_ids=[],
                    token_count=count_tokens(child_text)
                )
            )

        hierarchy, page, slide = _metadata_from_group(parent_group)

        parents.append(
            Chunk(
                chunk_id=parent_id,
                document_id=doc.document_id,
                chunk_index=parent_index,
                chunk_method="hierarchical_parent",
                text=parent_text,
                enterprise=doc.metadata.enterprise,
                source_filename=doc.metadata.source_filename,
                source_format=doc.metadata.source_format,
                section_hierarchy=hierarchy,
                page_number=page,
                slide_number=slide,
                parent_chunk_id=None,
                child_chunk_ids=child_ids,
                token_count=count_tokens(parent_text)
            )
        )

    # ================================================================
    # INTERNAL INVARIANTS
    # ================================================================

    if "".join(parent.text for parent in parents) != source_text:
        raise ValueError("Parents failed full source reconstruction")

    if "".join(child.text for child in children) != source_text:
        raise ValueError("Children failed full source reconstruction")

    if any(parent.token_count > PARENT_MAX_TOKENS for parent in parents):
        raise ValueError("Parent exceeds maximum token limit")

    if any(child.token_count > CHILD_MAX_TOKENS for child in children):
        raise ValueError("Child exceeds maximum token limit")

    parent_ids = {parent.chunk_id for parent in parents}
    child_ids = {child.chunk_id for child in children}

    if len(parent_ids) != len(parents) or len(child_ids) != len(children):
        raise ValueError("Duplicate hierarchical chunk IDs")

    if parent_ids & child_ids:
        raise ValueError("Parent and child chunk IDs must be distinct")

    if any(child.parent_chunk_id not in parent_ids for child in children):
        raise ValueError("Child references missing parent")

    # Check both directions in source order, including exact ownership.
    # A single cursor also ensures no children are omitted or reused.
    cursor = 0
    for parent in parents:
        count = len(parent.child_chunk_ids)
        assigned = children[cursor:cursor + count]
        if not assigned:
            raise ValueError("Parent has no children")
        if [child.chunk_id for child in assigned] != parent.child_chunk_ids:
            raise ValueError("Parent child IDs do not match child order")
        if any(child.parent_chunk_id != parent.chunk_id for child in assigned):
            raise ValueError("Parent-child links are inconsistent")
        if "".join(child.text for child in assigned) != parent.text:
            raise ValueError("Linked children do not reconstruct parent")
        cursor += count

    if cursor != len(children):
        raise ValueError("Unassigned hierarchical children")

    return parents, children
