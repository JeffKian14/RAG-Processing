import os
import glob

from src.parsers.docx_parser import convert_docx_to_normalized_document
from src.schemas import TextBlock, TableBlock, ListBlock


def print_list_structure(list_block, indent=6):
    prefix = " " * indent

    for item in list_block.items:
        text = item.text.replace("\n", " ")
        print(f"{prefix}- {text[:100]}")

        for sub_list in item.sub_lists:
            print(f"{prefix}  Nested List ({sub_list.list_type})")
            print_list_structure(sub_list, indent + 4)


def print_doc_summary(doc):
    print(f"\nDocument: {doc.metadata.source_filename}")
    print(f"Title: {doc.title}")
    print(f"Enterprise: {doc.metadata.enterprise}")

    text_blocks = sum(sum(1 for b in s.blocks if isinstance(b, TextBlock)) for s in doc.sections)
    list_blocks = sum(sum(1 for b in s.blocks if isinstance(b, ListBlock)) for s in doc.sections)
    table_blocks = sum(sum(1 for b in s.blocks if isinstance(b, TableBlock)) for s in doc.sections)

    print(f"Sections: {len(doc.sections)}")
    print(f"TextBlocks: {text_blocks}")
    print(f"ListBlocks: {list_blocks}")
    print(f"TableBlocks: {table_blocks}")

    print("\nSample Sections:")

    for section in doc.sections[:4]:
        print(f"\n  Hierarchy: {section.hierarchy}")
        print("  Blocks:")

        for block in section.blocks[:5]:
            if isinstance(block, TextBlock):
                snippet = block.text.replace("\n", " ")
                print(f"    TextBlock: {snippet[:100]}")

            elif isinstance(block, ListBlock):
                print(f"    ListBlock (type={block.list_type}, root_items={len(block.items)})")
                print_list_structure(block)

            elif isinstance(block, TableBlock):
                cols = len(block.headers) if block.headers else (len(block.rows[0]) if block.rows else 0)
                print(f"    TableBlock (cols={cols}, rows={len(block.rows)})")

                if block.headers:
                    print(f"      Headers: {block.headers}")

                for row in block.rows[:3]:
                    print(f"      Row: {row}")

        if len(section.blocks) > 5:
            print("    ...")


def has_nested_list(list_block):
    for item in list_block.items:
        if item.sub_lists:
            return True

        for sub_list in item.sub_lists:
            if has_nested_list(sub_list):
                return True

    return False


def table_has_empty_cell(table_block):
    if any(cell == "" for cell in table_block.headers):
        return True

    for row in table_block.rows:
        if any(cell == "" for cell in row):
            return True

    return False


def run_tests():
    print("=" * 72)
    print("STEP 7A: DOCX -> NORMALIZED DOCUMENT")
    print("=" * 72)

    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")

    if not os.path.exists(corpus_dir):
        corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")

    docx_files = glob.glob(os.path.join(corpus_dir, "**", "*.docx"), recursive=True)

    if not docx_files:
        print(f"No DOCX files found in: {corpus_dir}")
        return

    print(f"\nTotal DOCX discovered: {len(docx_files)}")

    targets = [
        "About Aventro Motors.docx",
        "Adaptive Cruise Control (ACC).docx",
        "Adjusting the Seat Positions.docx",
        "employee_handbook.docx",
    ]

    print("\n" + "=" * 72)
    print("REPRESENTATIVE DOCUMENT TESTS")
    print("=" * 72)

    for target in targets:
        docx_path = next((f for f in docx_files if target.lower() in os.path.basename(f).lower()), None)

        if not docx_path:
            print(f"\n[SKIP] Could not find: {target}")
            continue

        try:
            doc = convert_docx_to_normalized_document(docx_path)
            print_doc_summary(doc)

        except Exception as e:
            print(f"\n[ERROR] {target}: {e}")

    print("\n" + "=" * 72)
    print("MASS VALIDATION")
    print("=" * 72)

    success = 0
    failed = 0
    docs_with_nested_lists = 0
    docs_with_tables = 0
    docs_with_empty_cells = 0
    docs_with_lists = 0
    unknown_enterprise = 0
    empty_documents = 0

    failures = []

    for file_path in docx_files:
        try:
            doc = convert_docx_to_normalized_document(file_path)
            _ = doc.model_dump()

            has_list = False
            has_nested = False
            has_table = False
            has_empty = False
            total_blocks = 0

            for section in doc.sections:
                total_blocks += len(section.blocks)

                for block in section.blocks:
                    if isinstance(block, ListBlock):
                        has_list = True

                        if has_nested_list(block):
                            has_nested = True

                    elif isinstance(block, TableBlock):
                        has_table = True

                        if table_has_empty_cell(block):
                            has_empty = True

            if has_list:
                docs_with_lists += 1

            if has_nested:
                docs_with_nested_lists += 1

            if has_table:
                docs_with_tables += 1

            if has_empty:
                docs_with_empty_cells += 1

            if doc.metadata.enterprise == "Unknown":
                unknown_enterprise += 1

            if total_blocks == 0:
                empty_documents += 1

            success += 1

        except Exception as e:
            failed += 1
            failures.append((os.path.basename(file_path), str(e)))

    print(f"\nTotal DOCX files: {len(docx_files)}")
    print(f"Successfully normalized: {success}")
    print(f"Failed: {failed}")

    print("\nStructural Validation:")
    print(f"Documents with lists: {docs_with_lists}")
    print(f"Documents with nested lists: {docs_with_nested_lists}")
    print(f"Documents with tables: {docs_with_tables}")
    print(f"Documents preserving empty table cells: {docs_with_empty_cells}")
    print(f"Unknown enterprise: {unknown_enterprise}")
    print(f"Documents with 0 blocks: {empty_documents}")

    if failures:
        print("\nFailures:")

        for filename, error in failures[:20]:
            print(f"  {filename}: {error}")

    print("\n" + "=" * 72)

    if failed == 0 and unknown_enterprise == 0 and empty_documents == 0:
        print("MASS VALIDATION PASSED")
    else:
        print("MASS VALIDATION NEEDS REVIEW")

    print("=" * 72)


if __name__ == "__main__":
    run_tests()