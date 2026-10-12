import os
from collections import defaultdict

from src.chunking.units import build_chunk_units
from src.chunking.adaptive_chunker import (
    chunk_document,
    CHUNK_METHOD,
    MAX_TARGET_TOKENS,
    MAX_SAFE_TOKENS,
)
from src.chunking.chunk_test_utils import (
    get_corpus_files,
    parse_source,
    validate_common_chunk_fields,
    collect_common_chunk_stats,
    merge_error_counts,
    token_summary,
)
from src.chunking.utils import count_tokens


THRESHOLD_MULTIPLIER = 1.5


def new_stats():
    return {
        "docs": 0,
        "failed": 0,
        "chunks": 0,
        "physical_groups": 0,
        "split_groups": 0,
        "unsplit_groups": 0,
        "tokens": [],
        "empty": 0,
        "dup_id": 0,
        "idx_err": 0,
        "method_err": 0,
        "meta_err": 0,
        "token_err": 0,
        "id_err": 0,
        "provenance_err": 0,
        "preservation_err": 0,
        "order_err": 0,
        "cross_boundary_err": 0,
        "threshold_err": 0,
        "safety_limit_err": 0,
        "over_400": 0,
        "over_512": 0,
        "over_1024": 0,
        "hier": 0,
        "no_hier": 0,
        "pages": 0,
        "slides": 0,
    }


def build_physical_groups(
    units,
    mode,
):
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
                f"Missing {mode} provenance"
            )

        if current_id is None:
            current_id = provenance_id

        if provenance_id == current_id:
            current_units.append(unit)

        else:
            groups.append(
                (
                    current_id,
                    current_units,
                )
            )

            current_id = provenance_id
            current_units = [unit]

    if current_units:
        groups.append(
            (
                current_id,
                current_units,
            )
        )

    return groups


def normalize_text(text):
    return " ".join(
        text.split()
    )


def run_tests():

    print("=" * 72)
    print(
        "PHASE 8E-2 V2: "
        "ADAPTIVE PAGE/SLIDE CHUNKING VALIDATION"
    )
    print("=" * 72)

    paths = [
        path
        for path in get_corpus_files()
        if os.path.splitext(path)[1].lower()
        in (".pdf", ".pptx")
    ]

    stats = defaultdict(
        new_stats
    )

    failures = []
    seen_ids = set()

    for path in paths:

        ext = os.path.splitext(
            path
        )[1].lower()

        fmt = ext[1:].upper()

        stats[fmt]["docs"] += 1

        try:

            doc = parse_source(path)

            units = build_chunk_units(
                doc
            )

            mode = (
                "page"
                if fmt == "PDF"
                else "slide"
            )

            # ========================================================
            # ORIGINAL PHYSICAL GROUPS
            # ========================================================

            physical_groups = (
                build_physical_groups(
                    units,
                    mode,
                )
            )

            stats[fmt][
                "physical_groups"
            ] += len(
                physical_groups
            )

            group_sizes = []

            for (
                _,
                group_units,
            ) in physical_groups:

                text = "\n\n".join(
                    unit.text
                    for unit in group_units
                )

                group_sizes.append(
                    count_tokens(text)
                )

            if group_sizes:

                average_tokens = (
                    sum(group_sizes)
                    / len(group_sizes)
                )

                target_tokens = max(
                    1,
                    min(
                        round(
                            average_tokens
                        ),
                        MAX_TARGET_TOKENS,
                    ),
                )

                split_threshold = min(
                    average_tokens
                    * THRESHOLD_MULTIPLIER,
                    MAX_SAFE_TOKENS,
                )

            else:

                average_tokens = 0
                target_tokens = 0
                split_threshold = 0

            # ========================================================
            # RUN CHUNKER
            # ========================================================

            chunks = chunk_document(
                doc,
                large_threshold_multiplier=(
                    THRESHOLD_MULTIPLIER
                ),
            )

            # ========================================================
            # COMMON VALIDATION
            # ========================================================

            common_stats = (
                collect_common_chunk_stats(
                    chunks
                )
            )

            stats[fmt]["chunks"] += (
                common_stats["chunks"]
            )

            stats[fmt]["tokens"].extend(
                common_stats["tokens"]
            )

            stats[fmt]["hier"] += (
                common_stats["hier"]
            )

            stats[fmt]["no_hier"] += (
                common_stats["no_hier"]
            )

            stats[fmt]["pages"] += (
                common_stats["pages"]
            )

            stats[fmt]["slides"] += (
                common_stats["slides"]
            )

            common_errors = (
                validate_common_chunk_fields(
                    doc,
                    chunks,
                    CHUNK_METHOD,
                    seen_ids,
                )
            )

            merge_error_counts(
                stats[fmt],
                common_errors,
            )

            # ========================================================
            # GROUP OUTPUT BACK BY PHYSICAL PROVENANCE
            # ========================================================

            chunks_by_provenance = (
                defaultdict(list)
            )

            previous_provenance = None

            finished_provenance = set()

            for chunk in chunks:

                provenance_id = (
                    chunk.page_number
                    if mode == "page"
                    else chunk.slide_number
                )

                if provenance_id is None:

                    stats[fmt][
                        "provenance_err"
                    ] += 1

                    continue

                # ----------------------------------------------------
                # Ensure we never leave a physical page/slide and
                # later return to it.
                # ----------------------------------------------------

                if (
                    previous_provenance
                    is not None
                    and provenance_id
                    != previous_provenance
                ):

                    finished_provenance.add(
                        previous_provenance
                    )

                if (
                    provenance_id
                    in finished_provenance
                ):

                    stats[fmt][
                        "order_err"
                    ] += 1

                previous_provenance = (
                    provenance_id
                )

                chunks_by_provenance[
                    provenance_id
                ].append(chunk)

                # ----------------------------------------------------
                # Correct provenance type
                # ----------------------------------------------------

                if mode == "page":

                    if (
                        chunk.slide_number
                        is not None
                    ):
                        stats[fmt][
                            "provenance_err"
                        ] += 1

                else:

                    if (
                        chunk.page_number
                        is not None
                    ):
                        stats[fmt][
                            "provenance_err"
                        ] += 1

                # ----------------------------------------------------
                # TOKEN STATISTICS
                # ----------------------------------------------------

                if chunk.token_count > 400:
                    stats[fmt][
                        "over_400"
                    ] += 1

                if chunk.token_count > 512:
                    stats[fmt][
                        "over_512"
                    ] += 1

                if chunk.token_count > 1024:
                    stats[fmt][
                        "over_1024"
                    ] += 1

                # ----------------------------------------------------
                # Absolute safety rule
                # ----------------------------------------------------

                if (
                    chunk.token_count
                    > MAX_SAFE_TOKENS
                ):
                    stats[fmt][
                        "safety_limit_err"
                    ] += 1

            # ========================================================
            # CHECK EACH ORIGINAL PHYSICAL GROUP
            # ========================================================

            for (
                provenance_id,
                group_units,
            ) in physical_groups:

                original_text = (
                    "\n\n".join(
                        unit.text
                        for unit
                        in group_units
                    )
                )

                original_tokens = (
                    count_tokens(
                        original_text
                    )
                )

                produced_chunks = (
                    chunks_by_provenance.get(
                        provenance_id,
                        [],
                    )
                )

                if not produced_chunks:

                    stats[fmt][
                        "preservation_err"
                    ] += 1

                    continue

                # ----------------------------------------------------
                # EXPECTED SPLIT BEHAVIOR
                # ----------------------------------------------------

                should_split = (
                    original_tokens
                    > split_threshold
                )

                if should_split:

                    if (
                        len(
                            produced_chunks
                        )
                        > 1
                    ):

                        stats[fmt][
                            "split_groups"
                        ] += 1

                    else:

                        stats[fmt][
                            "threshold_err"
                        ] += 1

                else:

                    stats[fmt][
                        "unsplit_groups"
                    ] += 1

                    if (
                        len(
                            produced_chunks
                        )
                        != 1
                    ):

                        stats[fmt][
                            "threshold_err"
                        ] += 1

                # ----------------------------------------------------
                # CONTENT PRESERVATION
                # ----------------------------------------------------

                reconstructed_text = (
                    "\n\n".join(
                        chunk.text
                        for chunk
                        in produced_chunks
                    )
                )

                if (
                    normalize_text(
                        reconstructed_text
                    )
                    != normalize_text(
                        original_text
                    )
                ):

                    stats[fmt][
                        "preservation_err"
                    ] += 1

                # ----------------------------------------------------
                # PROVENANCE PRESERVATION
                # ----------------------------------------------------

                for chunk in produced_chunks:

                    chunk_pid = (
                        chunk.page_number
                        if mode == "page"
                        else chunk.slide_number
                    )

                    if (
                        chunk_pid
                        != provenance_id
                    ):

                        stats[fmt][
                            "cross_boundary_err"
                        ] += 1

                # ----------------------------------------------------
                # Split chunks should target <= target_tokens.
                #
                # Unsplit physical groups can be larger than the
                # target, but never larger than MAX_SAFE_TOKENS.
                # ----------------------------------------------------

                if should_split:

                    for chunk in produced_chunks:

                        if (
                            chunk.token_count
                            > target_tokens
                        ):

                            stats[fmt][
                                "threshold_err"
                            ] += 1

        except Exception as e:

            stats[fmt][
                "failed"
            ] += 1

            if len(failures) < 20:

                failures.append(
                    f"{fmt} | "
                    f"{os.path.basename(path)} | "
                    f"{type(e).__name__}: {e}"
                )

    # ================================================================
    # PER-FORMAT REPORT
    # ================================================================

    for fmt in [
        "PDF",
        "PPTX",
    ]:

        s = stats[fmt]

        minimum, average, maximum = (
            token_summary(
                s["tokens"]
            )
        )

        print(
            f"\n{fmt}"
        )

        print(
            f"Documents: "
            f"{s['docs']}"
        )

        print(
            f"Failed: "
            f"{s['failed']}"
        )

        print(
            f"Physical groups: "
            f"{s['physical_groups']}"
        )

        print(
            f"Chunks: "
            f"{s['chunks']}"
        )

        print(
            f"Split physical groups: "
            f"{s['split_groups']}"
        )

        print(
            f"Unsplit physical groups: "
            f"{s['unsplit_groups']}"
        )

        print(
            f"Min/Avg/Max tokens: "
            f"{minimum} / "
            f"{average:.1f} / "
            f"{maximum}"
        )

        print(
            f"Chunks >400: "
            f"{s['over_400']}"
        )

        print(
            f"Chunks >512: "
            f"{s['over_512']}"
        )

    # ================================================================
    # TOTALS
    # ================================================================

    total = {
        key: 0
        for key in new_stats()
        if key != "tokens"
    }

    for fmt in [
        "PDF",
        "PPTX",
    ]:

        for key in total:

            total[key] += (
                stats[fmt][key]
            )

    all_tokens = [
        token
        for fmt in [
            "PDF",
            "PPTX",
        ]
        for token
        in stats[fmt]["tokens"]
    ]

    minimum, average, maximum = (
        token_summary(
            all_tokens
        )
    )

    print(
        "\n"
        + "-" * 72
    )

    print("TOTAL")

    print(
        f"Documents: "
        f"{total['docs']}"
    )

    print(
        f"Failed: "
        f"{total['failed']}"
    )

    print(
        f"Physical groups: "
        f"{total['physical_groups']}"
    )

    print(
        f"Chunks: "
        f"{total['chunks']}"
    )

    print(
        f"Split physical groups: "
        f"{total['split_groups']}"
    )

    print(
        f"Unsplit physical groups: "
        f"{total['unsplit_groups']}"
    )

    print(
        f"Min/Avg/Max tokens: "
        f"{minimum} / "
        f"{average:.1f} / "
        f"{maximum}"
    )

    print()

    print(
        f"Empty chunks: "
        f"{total['empty']}"
    )

    print(
        f"Duplicate IDs: "
        f"{total['dup_id']}"
    )

    print(
        f"Index errors: "
        f"{total['idx_err']}"
    )

    print(
        f"Method errors: "
        f"{total['method_err']}"
    )

    print(
        f"Metadata errors: "
        f"{total['meta_err']}"
    )

    print(
        f"Token-count errors: "
        f"{total['token_err']}"
    )

    print(
        f"Chunk-ID errors: "
        f"{total['id_err']}"
    )

    print()

    print(
        f"Provenance errors: "
        f"{total['provenance_err']}"
    )

    print(
        f"Content preservation errors: "
        f"{total['preservation_err']}"
    )

    print(
        f"Order errors: "
        f"{total['order_err']}"
    )

    print(
        f"Cross-boundary errors: "
        f"{total['cross_boundary_err']}"
    )

    print(
        f"Threshold behavior errors: "
        f"{total['threshold_err']}"
    )

    print(
        f"Safety-limit errors: "
        f"{total['safety_limit_err']}"
    )

    print()

    print(
        f"Chunks >400: "
        f"{total['over_400']}"
    )

    print(
        f"Chunks >512: "
        f"{total['over_512']}"
    )

    print(
        f"Chunks >1024: "
        f"{total['over_1024']}"
    )

    print()

    print(
        f"Chunks with hierarchy: "
        f"{total['hier']}"
    )

    print(
        f"Chunks without hierarchy: "
        f"{total['no_hier']}"
    )

    print(
        f"Page-numbered chunks: "
        f"{total['pages']}"
    )

    print(
        f"Slide-numbered chunks: "
        f"{total['slides']}"
    )

    print(
        "-" * 72
    )

    if failures:

        print(
            "\nFirst failures:"
        )

        for failure in failures:

            print(
                f"  - {failure}"
            )

    # ================================================================
    # PASS / FAIL
    # ================================================================

    error_keys = [
        "failed",
        "empty",
        "dup_id",
        "idx_err",
        "method_err",
        "meta_err",
        "token_err",
        "id_err",
        "provenance_err",
        "preservation_err",
        "order_err",
        "cross_boundary_err",
        "threshold_err",
        "safety_limit_err",
    ]

    critical_errors = sum(
        total[key]
        for key in error_keys
    )

    print(
        "\nADAPTIVE PAGE/SLIDE V2 "
        "VALIDATION "
        + (
            "PASSED"
            if critical_errors == 0
            else "NEEDS REVIEW"
        )
    )

    print(
        "=" * 72
    )


if __name__ == "__main__":
    run_tests()