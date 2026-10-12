from typing import List

from src.schemas import NormalizedDocument, Chunk
from src.chunking.units import build_chunk_units
from src.chunking.utils import (
    count_tokens,
    split_text_by_tokens,
    generate_chunk_id,
    longest_common_hierarchy,
)


CHUNK_METHOD = "adaptive_page_slide"

MAX_TARGET_TOKENS = 400
MAX_SAFE_TOKENS = 512


def chunk_document(
    doc: NormalizedDocument,
    large_threshold_multiplier: float = 1.5,
) -> List[Chunk]:

    if large_threshold_multiplier <= 1.0:
        raise ValueError(
            "large_threshold_multiplier must be greater than 1.0"
        )

    units = build_chunk_units(doc)

    if not units:
        return []

    # ================================================================
    # 1. DETERMINE PAGE OR SLIDE MODE
    # ================================================================

    has_pages = any(
        unit.page_number is not None
        for unit in units
    )

    has_slides = any(
        unit.slide_number is not None
        for unit in units
    )

    if has_pages:
        mode = "page"

    elif has_slides:
        mode = "slide"

    else:
        raise ValueError(
            "Adaptive page/slide chunking requires "
            "page or slide provenance"
        )

    # ================================================================
    # 2. GROUP UNITS BY PHYSICAL PAGE / SLIDE
    # ================================================================

    groups = []

    current_id = None
    current_units = []

    for unit in units:

        provenance_id = (
            unit.page_number
            if mode == "page"
            else unit.slide_number
        )

        if provenance_id is None:
            raise ValueError(
                f"Missing provenance in {mode} mode"
            )

        if current_id is None:
            current_id = provenance_id

        if provenance_id == current_id:
            current_units.append(unit)

        else:
            groups.append(
                (current_id, current_units)
            )

            current_id = provenance_id
            current_units = [unit]

    if current_units:
        groups.append(
            (current_id, current_units)
        )

    # ================================================================
    # 3. CALCULATE DOCUMENT-LEVEL ADAPTIVE SIZE
    # ================================================================

    group_token_sizes = []

    for _, group_units in groups:

        group_text = "\n\n".join(
            unit.text
            for unit in group_units
        )

        group_token_sizes.append(
            count_tokens(group_text)
        )

    average_tokens = (
        sum(group_token_sizes)
        / len(group_token_sizes)
    )

    # ------------------------------------------------------------
    # Target:
    # Try to split toward the document's natural average,
    # but never target chunks larger than 400 tokens.
    # ------------------------------------------------------------

    target_tokens = max(
        1,
        min(
            round(average_tokens),
            MAX_TARGET_TOKENS,
        ),
    )

    # ------------------------------------------------------------
    # Threshold:
    # A page/slide is considered unusually large when it is
    # > 1.5 × document average.
    #
    # However, 512 is the absolute safety limit.
    # ------------------------------------------------------------

    split_threshold = min(
        average_tokens * large_threshold_multiplier,
        MAX_SAFE_TOKENS,
    )

    # ================================================================
    # 4. PROCESS PHYSICAL GROUPS
    # ================================================================

    chunk_parts = []

    for provenance_id, group_units in groups:

        full_text = "\n\n".join(
            unit.text
            for unit in group_units
        )

        full_token_count = count_tokens(
            full_text
        )

        # ------------------------------------------------------------
        # Normal-sized page / slide:
        # keep it intact.
        # ------------------------------------------------------------

        if full_token_count <= split_threshold:

            chunk_parts.append((
                full_text,
                [
                    unit.section_hierarchy
                    for unit in group_units
                ],
                provenance_id,
            ))

            continue

        # ------------------------------------------------------------
        # Large physical group:
        # split toward target_tokens.
        # ------------------------------------------------------------

        current_texts = []
        current_hierarchies = []

        def flush():
            if not current_texts:
                return

            text = "\n\n".join(
                current_texts
            )

            chunk_parts.append((
                text,
                list(current_hierarchies),
                provenance_id,
            ))

            current_texts.clear()
            current_hierarchies.clear()

        for unit in group_units:

            # --------------------------------------------------------
            # A single semantic unit can itself be larger than the
            # target. Reuse the existing locked token splitter.
            # --------------------------------------------------------

            fragments = split_text_by_tokens(
                unit.text,
                target_tokens,
            )

            for fragment in fragments:

                if not current_texts:

                    current_texts.append(
                        fragment
                    )

                    current_hierarchies.append(
                        unit.section_hierarchy
                    )

                    continue

                candidate = "\n\n".join(
                    current_texts
                    + [fragment]
                )

                if (
                    count_tokens(candidate)
                    <= target_tokens
                ):

                    current_texts.append(
                        fragment
                    )

                    current_hierarchies.append(
                        unit.section_hierarchy
                    )

                else:

                    flush()

                    current_texts.append(
                        fragment
                    )

                    current_hierarchies.append(
                        unit.section_hierarchy
                    )

        flush()

    # ================================================================
    # 5. BUILD FINAL CHUNKS
    # ================================================================

    chunks = []

    for (
        text,
        hierarchies,
        provenance_id,
    ) in chunk_parts:

        chunk_index = len(chunks)

        chunks.append(
            Chunk(
                chunk_id=generate_chunk_id(
                    doc.document_id,
                    CHUNK_METHOD,
                    chunk_index,
                    text,
                ),
                document_id=doc.document_id,
                chunk_index=chunk_index,
                chunk_method=CHUNK_METHOD,
                text=text,
                enterprise=doc.metadata.enterprise,
                source_filename=doc.metadata.source_filename,
                source_format=doc.metadata.source_format,
                section_hierarchy=longest_common_hierarchy(
                    hierarchies
                ),
                page_number=(
                    provenance_id
                    if mode == "page"
                    else None
                ),
                slide_number=(
                    provenance_id
                    if mode == "slide"
                    else None
                ),
                parent_chunk_id=None,
                child_chunk_ids=[],
                token_count=count_tokens(text),
            )
        )

    return chunks