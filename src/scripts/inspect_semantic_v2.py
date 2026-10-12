
import os
import random

from src.chunking.chunk_test_utils import FORMATS, get_corpus_files, parse_source
from src.chunking.semantic_chunker_v2 import chunk_document


SEED = 42
DOCS_PER_FORMAT = 4
MAX_TEXT_LENGTH = 2000


def print_chunk(title, chunk):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(f"File: {chunk.source_filename}")
    print(f"Format: {chunk.source_format}")
    print(f"Tokens: {chunk.token_count}")
    print(f"Hierarchy: {chunk.section_hierarchy}")
    print(f"Page: {chunk.page_number}")
    print(f"Slide: {chunk.slide_number}")
    print("-" * 100)

    text = chunk.text

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n...[TRUNCATED FOR DISPLAY]"

    print(repr(text))
    print()


def main():
    random.seed(SEED)

    files_by_format = {fmt: [] for fmt in FORMATS}

    for path in get_corpus_files():
        fmt = os.path.splitext(path)[1][1:].upper()

        if fmt in FORMATS:
            files_by_format[fmt].append(path)

    # ----------------------------------------------------------------
    # 1. NORMAL RANDOM SAMPLE
    # ----------------------------------------------------------------

    print("\n" + "#" * 100)
    print("SEMANTIC V2 — RANDOM COHERENCE INSPECTION")
    print("#" * 100)

    sample_number = 1

    for fmt in FORMATS:
        paths = random.sample(files_by_format[fmt], min(DOCS_PER_FORMAT, len(files_by_format[fmt])))

        for path in paths:
            doc = parse_source(path)
            chunks = chunk_document(doc)

            if not chunks:
                continue

            chunk = random.choice(chunks)
            print_chunk(f"SAMPLE {sample_number}/20 — {fmt}", chunk)
            sample_number += 1

    # ----------------------------------------------------------------
    # 2. CROSS-PAGE PDF EXAMPLES
    # ----------------------------------------------------------------

    print("\n" + "#" * 100)
    print("PDF CROSS-PAGE INSPECTION")
    print("#" * 100)

    found = 0

    for path in files_by_format["PDF"]:
        doc = parse_source(path)

        for chunk in chunk_document(doc):
            if chunk.page_number is None:
                print_chunk(f"PDF CROSS-PAGE #{found + 1}", chunk)
                found += 1

                if found >= 3:
                    break

        if found >= 3:
            break

    # ----------------------------------------------------------------
    # 3. CROSS-SLIDE PPTX EXAMPLES
    # ----------------------------------------------------------------

    print("\n" + "#" * 100)
    print("PPTX CROSS-SLIDE INSPECTION")
    print("#" * 100)

    found = 0

    for path in files_by_format["PPTX"]:
        doc = parse_source(path)

        for chunk in chunk_document(doc):
            if chunk.slide_number is None:
                print_chunk(f"PPTX CROSS-SLIDE #{found + 1}", chunk)
                found += 1

                if found >= 3:
                    break

        if found >= 3:
            break


if __name__ == "__main__":
    main()