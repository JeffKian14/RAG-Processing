"""Standalone structure-aware source chunking with a separate retrieval view.

Uses only normalized sections and blocks; no embeddings or other chunkers.
Whole structural units are packed near the target, with optional whole-unit
overlap. The hard maximum includes supplementary retrieval context. If context
would force an otherwise-fitting source unit to split, context is omitted
(section labels before table labels) and context_truncated reports that loss.
"""
from dataclasses import dataclass
from typing import List, Tuple

from src.schemas import NormalizedDocument, StructureAwareChunk, TableBlock, ListBlock
from src.chunking.render import render_block, render_list
from src.chunking.utils import count_tokens, generate_chunk_id, longest_common_hierarchy


TARGET_TOKENS = 220
MAX_TOKENS = 400
OVERLAP_TOKENS = 80
SEPARATORS = ("\n\n", "\n", ". ", "; ", ", ", " ")


@dataclass(frozen=True)
class _Block:
    start: int
    content_start: int
    end: int
    hierarchy: Tuple[str, ...]
    page: int | None
    slide: int | None
    header: str = ""
    header_end: int = 0


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    block: _Block
    whole: bool = True


def _records(block, raw: str):
    """Return exact structural records; multiline cells/nested items stay whole."""
    if isinstance(block, TableBlock):
        parts = ([" | ".join(block.headers)] if block.headers else [])
        parts += [" | ".join(row) for row in block.rows]
        return parts, "\n"
    if isinstance(block, ListBlock):
        parts = []
        for index, item in enumerate(block.items, 1):
            prefix = f"{index}. " if block.list_type == "ordered" else "- "
            lines = [prefix + item.text]
            lines.extend(render_list(sub, 1) for sub in item.sub_lists)
            parts.append("\n".join(lines))
        return parts, "\n"
    return raw.split("\n\n"), "\n\n"


def _source_and_units(doc: NormalizedDocument):
    """Match build_chunk_units' canonical rendering, with exact record offsets."""
    texts, blocks, units = [], [], []
    cursor = 0
    for section in doc.sections:
        for block in section.blocks:
            raw = render_block(block)
            text = raw.strip()
            if not text:
                continue
            prefix = "\n\n" if texts else ""
            start = cursor
            content_start = start + len(prefix)
            cursor = content_start + len(text)
            trim_start = len(raw) - len(raw.lstrip())
            trim_end = len(raw.rstrip())
            header = " | ".join(block.headers) if isinstance(block, TableBlock) and block.headers else ""
            span = _Block(start, content_start, cursor, tuple(section.hierarchy),
                          block.page_number, block.slide_number, header,
                          content_start + max(0, len(header) - trim_start))
            blocks.append(span)
            texts.append(prefix + text)
            records, separator = _records(block, raw)
            if separator.join(records) != raw:
                raise ValueError("Structural records differ from canonical block rendering")
            # Place separators on the next record. Empty records are attached
            # to a neighboring nonempty record rather than emitted alone.
            ends, position = [], 0
            for record in records:
                position += len(record)
                if record.strip():
                    ends.append(position)
                position += len(separator)
            cuts = [trim_start] + [end for end in ends[:-1] if trim_start < end < trim_end] + [trim_end]
            for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
                unit_start = start if index == 0 else content_start + left - trim_start
                unit_end = content_start + right - trim_start
                if unit_end > unit_start:
                    units.append(_Unit(unit_start, unit_end, span))
    source = "".join(texts)
    if "".join(source[u.start:u.end] for u in units) != source:
        raise ValueError("Structural units failed exact source reconstruction")
    return source, blocks, units


def _split_exact(text: str, cap: int, separators=SEPARATORS) -> List[str]:
    """Split only oversized units, retaining every source character."""
    if count_tokens(text) <= cap:
        return [text]
    if separators:
        sep = separators[0]
        parts = text.split(sep)
        pieces = [part + sep for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
        if len(pieces) <= 1:
            return _split_exact(text, cap, separators[1:])
        result, current = [], ""
        for piece in pieces:
            if count_tokens(current + piece) <= cap:
                current += piece
                continue
            if current.strip():
                result.append(current)
                current = ""
            # Keep a leading separator attached to actual source content.
            piece = current + piece
            current = ""
            if count_tokens(piece) > cap:
                result.extend(_split_exact(piece, cap, separators[1:]))
            else:
                current = piece
        if current:
            if not current.strip() and result:
                result[-1] += current
            else:
                result.append(current)
        return result
    result = []
    while text:
        if count_tokens(text) <= cap:
            result.append(text)
            break
        low, high, best = 1, len(text), 0
        while low <= high:
            mid = (low + high) // 2
            if count_tokens(text[:mid]) <= cap:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if not best:
            raise ValueError("Token budget cannot fit a source character")
        result.append(text[:best])
        text = text[best:]
    return result


def _prepare_units(source, units, target, maximum):
    prepared = []
    for unit in units:
        text = source[unit.start:unit.end]
        if count_tokens(text) <= maximum:
            prepared.append(unit)
            continue
        fragments = _split_exact(text, target)
        if "".join(fragments) != text or any(count_tokens(t) > maximum for t in fragments):
            raise ValueError("Oversized-unit splitting failed its source or size contract")
        cursor = unit.start
        for fragment in fragments:
            prepared.append(_Unit(cursor, cursor + len(fragment), unit.block, False))
            cursor += len(fragment)
    return prepared


def _compatible(left, right):
    """Only identical hierarchy paths or immediate siblings are compatible."""
    return left == right or len(left) > 1 and len(right) > 1 and left[:-1] == right[:-1]


def _retrieval_view(source, blocks, start, end, maximum, allow_omission=False):
    """Insert labelled context at the relevant source block, never into text."""
    segments = []
    last_hierarchy = None
    for block in blocks:
        if block.end <= start or block.start >= end:
            continue
        if block.hierarchy and block.hierarchy != last_hierarchy:
            segments.append(("section", "[Section: " + " > ".join(block.hierarchy) + "]\n"))
        last_hierarchy = block.hierarchy
        if block.header and not (start <= block.content_start and end >= block.header_end):
            segments.append(("table", "[Table columns: " + block.header + "]\n"))
        segments.append(("source", source[max(start, block.start):min(end, block.end)]))
    omitted = set()
    text = "".join(value for _, value in segments)
    if allow_omission and count_tokens(text) > maximum:
        for kind in ("section", "table"):
            for index in range(len(segments) - 1, -1, -1):
                if segments[index][0] == kind:
                    omitted.add(index)
                    text = "".join(value for i, (_, value) in enumerate(segments) if i not in omitted)
                    if count_tokens(text) <= maximum:
                        return text, True
    return text, bool(omitted)


def _overlap_start(source, units, new_start, previous_new_start, cap):
    """Reuse only a whole-unit suffix of the previous chunk's new content."""
    start = new_start
    if not cap:
        return start
    for index in range(new_start - 1, previous_new_start - 1, -1):
        if not units[index].whole:
            break
        text = source[units[index].start:units[new_start - 1].end]
        if count_tokens(text) > cap:
            break
        start = index
    return start


def _emit(doc, source, blocks, group, start, end, new_start, index, retrieval, omitted):
    selected = group[start:end]
    left, right = selected[0].start, selected[-1].end
    text = source[left:right]
    contributors = [b for b in blocks if b.end > left and b.start < right]
    paths = []
    for block in contributors:
        path = list(block.hierarchy)
        if path not in paths:
            paths.append(path)
    pages = [b.page for b in contributors]
    slides = [b.slide for b in contributors]
    return StructureAwareChunk(
        chunk_id=generate_chunk_id(doc.document_id, "structure_aware", index, text),
        document_id=doc.document_id, chunk_index=index, chunk_method="structure_aware",
        text=text, token_count=count_tokens(text),
        enterprise=doc.metadata.enterprise, source_filename=doc.metadata.source_filename,
        source_format=doc.metadata.source_format,
        section_hierarchy=longest_common_hierarchy(paths),
        page_number=pages[0] if pages and pages[0] is not None and len(set(pages)) == 1 else None,
        slide_number=slides[0] if slides and slides[0] is not None and len(set(slides)) == 1 else None,
        retrieval_text=retrieval, retrieval_token_count=count_tokens(retrieval),
        source_start_char=left, source_end_char=right,
        source_pages=sorted({p for p in pages if p is not None}),
        source_slides=sorted({s for s in slides if s is not None}),
        source_section_hierarchies=paths,
        overlap_tokens=count_tokens(source[left:group[new_start].start]),
        context_truncated=omitted, has_split_unit=any(not u.whole for u in selected),
    )


def chunk_document(doc: NormalizedDocument, target_tokens: int = TARGET_TOKENS, 
                   max_tokens: int = MAX_TOKENS, overlap_tokens: int = OVERLAP_TOKENS) -> List[StructureAwareChunk]:
    """Return flat source chunks and supplementary retrieval representations.

    Target/max count retrieval_text, including overlap and context. Whole
    paragraphs, root list items with their nested content, and table rows are
    retained when they fit the source maximum. No cross-topic overlap occurs.
    Missing source provenance is never inferred. The greedy packing preference
    is closeness to target at structural boundaries, not a semantic score.
    """
    if any(type(v) is not int for v in (target_tokens, max_tokens, overlap_tokens)):
        raise ValueError("Token settings must be integers")
    if not 0 < target_tokens <= max_tokens or not 0 <= overlap_tokens < target_tokens:
        raise ValueError("Require 0 < target <= maximum and 0 <= overlap < target")
    source, blocks, units = _source_and_units(doc)
    units = _prepare_units(source, units, target_tokens, max_tokens)
    groups = []
    for unit in units:
        if groups and _compatible(groups[-1][-1].block.hierarchy, unit.block.hierarchy):
            groups[-1].append(unit)
        else:
            groups.append([unit])
    chunks = []
    for group in groups:
        cursor = previous_new_start = 0
        while cursor < len(group):
            start = _overlap_start(source, group, cursor, previous_new_start, overlap_tokens)
            end = cursor + 1
            retrieval, omitted = _retrieval_view(source, blocks, group[start].start, group[end - 1].end, max_tokens)
            while start < cursor and count_tokens(retrieval) > max_tokens:
                start += 1
                retrieval, omitted = _retrieval_view(source, blocks, group[start].start, group[end - 1].end, max_tokens)
            if count_tokens(retrieval) > max_tokens:
                retrieval, omitted = _retrieval_view(source, blocks, group[start].start, group[end - 1].end, max_tokens, True)
            if count_tokens(retrieval) > max_tokens:
                raise ValueError("Cannot fit a source unit in the retrieval budget")
            # Preserve an otherwise-fitting unit even when it exceeds target.
            # Extra units are added only when the complete view moves closer
            # to target, without dropping supplementary context to pack more.
            while end < len(group) and not omitted:
                candidate, _ = _retrieval_view(source, blocks, group[start].start, group[end].end, max_tokens)
                size = count_tokens(candidate)
                if size > max_tokens or abs(size - target_tokens) > abs(count_tokens(retrieval) - target_tokens):
                    break
                retrieval = candidate
                end += 1
            chunks.append(_emit(doc, source, blocks, group, start, end, cursor, len(chunks), retrieval, omitted))
            previous_new_start, cursor = cursor, end
    covered, ids = 0, set()
    for chunk in chunks:
        if not chunk.text.strip() or not chunk.source_start_char <= covered < chunk.source_end_char:
            raise ValueError("Chunking lost coverage or failed to add source content")
        if chunk.retrieval_token_count > max_tokens or chunk.overlap_tokens > overlap_tokens:
            raise ValueError("Chunk exceeds retrieval or overlap maximum")
        if chunk.chunk_id in ids:
            raise ValueError("Duplicate structure-aware chunk ID")
        ids.add(chunk.chunk_id)
        covered = chunk.source_end_char
    if covered != len(source):
        raise ValueError("Chunking did not cover the complete canonical source")
    return chunks
