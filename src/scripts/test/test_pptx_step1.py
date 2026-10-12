import os
import glob
from collections import Counter

from src.parsers.pptx_parser import convert_pptx_to_normalized_document
from src.schemas import TextBlock, ListBlock, TableBlock


def walk_list(block):
    count = len(block.items)
    for item in block.items:
        for sub in item.sub_lists: count += walk_list(sub)
    return count


def main():
    corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus): corpus = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")

    files = glob.glob(os.path.join(corpus, "**", "*.pptx"), recursive=True)
    stats = Counter()
    failures = []

    for path in files:
        try:
            doc = convert_pptx_to_normalized_document(path)
            stats["documents"] += 1
            stats["sections"] += len(doc.sections)

            for section in doc.sections:
                for block in section.blocks:
                    if isinstance(block, TextBlock): stats["text_blocks"] += 1
                    elif isinstance(block, ListBlock):
                        stats["list_blocks"] += 1
                        stats["list_items"] += walk_list(block)
                    elif isinstance(block, TableBlock): stats["table_blocks"] += 1

        except Exception as e:
            failures.append((os.path.basename(path), str(e)))

    print("=" * 72)
    print("PPTX BASIC NORMALIZATION TEST")
    print("=" * 72)
    print(f"Total PPTX: {len(files)}")
    print(f"Normalized: {stats['documents']}")
    print(f"Failed: {len(failures)}")
    print(f"Sections: {stats['sections']}")
    print(f"TextBlocks: {stats['text_blocks']}")
    print(f"ListBlocks: {stats['list_blocks']}")
    print(f"ListItems: {stats['list_items']}")
    print(f"TableBlocks: {stats['table_blocks']}")

    if failures:
        print("\nFailures:")
        for filename, error in failures[:20]: print(f"  {filename}: {error}")

    print("=" * 72)


if __name__ == "__main__": main()