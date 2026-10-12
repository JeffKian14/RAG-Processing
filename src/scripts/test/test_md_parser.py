# --- src/scripts/test_md_parser.py ---
import os
import glob
from src.schemas import DocumentMetadata, NormalizedDocument
from src.parsers.markdown_parser import parse_markdown_to_normalized

def print_debug_inspection(doc: NormalizedDocument):
    """Prints a visual representation of the NormalizedDocument."""
    print(f"\n{'='*50}")
    print(f"DOCUMENT ID : {doc.document_id}")
    print(f"TITLE       : {doc.title}")
    print(f"ENTERPRISE  : {doc.metadata.enterprise}")
    print(f"FILE        : {doc.metadata.source_filename}")
    print(f"{'='*50}")
    
    for i, section in enumerate(doc.sections):
        hierarchy_str = " > ".join(section.hierarchy) if section.hierarchy else "[Root / No Heading]"
        print(f"\nSECTION {i+1}: {hierarchy_str}")
        
        for block in section.blocks:
            if block.block_type == "text":
                # Truncate text for clean terminal viewing
                text_preview = block.text.replace("\n", " ")
                if len(text_preview) > 75:
                    text_preview = text_preview[:72] + "..."
                print(f"  [TEXT]  {text_preview}")
                
            elif block.block_type == "table":
                print(f"  [TABLE]")
                print(f"    ├─ Headers : {block.headers}")
                print(f"    └─ Rows    : {len(block.rows)} rows extracted")
                if block.rows:
                    print(f"       (Row 1 preview: {block.rows[0]})")

def run_sample_test(dataset_root: str, sample_size: int = 3):
    """Finds a few Markdown files from different enterprises and tests the parser."""
    
    # Grab a few MD files from different enterprises
    search_pattern = os.path.join(dataset_root, "datasets", "*", "md", "*.md")
    md_files = glob.glob(search_pattern)[:sample_size]
    
    if not md_files:
        print(f"No Markdown files found in {search_pattern}")
        return

    for filepath in md_files:
        # Extract enterprise name from the path for dummy metadata
        parts = filepath.replace("\\", "/").split("/")
        enterprise = parts[-3] if len(parts) >= 3 else "Unknown"
        filename = parts[-1]
        
        meta = DocumentMetadata(
            enterprise=enterprise,
            source_filename=filename,
            source_format="md"
        )
        
        # We need a slight patch to the parser's table detection to catch standard MD tables:
        # Change: `if stripped_line.startswith('|') and stripped_line.endswith('|'):`
        # To:     `if '|' in stripped_line and not stripped_line.startswith('#'):` 
        # (Assuming you applied this quick patch in markdown_parser.py)
        
        try:
            doc = parse_markdown_to_normalized(
                file_path=filepath,
                document_id=f"test_{filename}",
                metadata=meta
            )
            print_debug_inspection(doc)
        except Exception as e:
            print(f"\n[ERROR] Failed to parse {filename}: {e}")

if __name__ == "__main__":
    # Adjust this path to point to your unzipped RAG-Multi-Corpus dataset
    DATASET_PATH = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main" 
    run_sample_test(DATASET_PATH, sample_size=3)