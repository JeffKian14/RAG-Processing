import os
import glob
from src.schemas import DocumentMetadata, TableBlock
from src.parsers.markdown_parser import parse_markdown_to_normalized

def is_suspicious_table(table: TableBlock) -> tuple[bool, list[str]]:
    """Evaluates a table against heuristics to determine if it might be a false positive."""
    reasons = []
    
    # 1. No data rows (just a header)
    if not table.rows:
        reasons.append("0 data rows (header only)")
        
    # 2. Single column (often just a line of text that started/ended with a pipe)
    if len(table.headers) <= 1:
        reasons.append("Only 1 column")
        
    # 3. Exceptionally long cells (likely normal prose interrupted by a pipe)
    max_len = 0
    for cell in table.headers:
        max_len = max(max_len, len(cell))
    for row in table.rows:
        for cell in row:
            max_len = max(max_len, len(cell))
            
    if max_len > 120:
        reasons.append(f"Contains very long text cell ({max_len} chars)")

    return len(reasons) > 0, reasons

def run_table_diagnostic(dataset_root: str):
    search_pattern = os.path.join(dataset_root, "datasets", "*", "md", "*.md")
    md_files = glob.glob(search_pattern)

    total_tables = 0
    suspicious_tables = 0

    print("Running Table Diagnostic...\n" + "="*50)

    for filepath in md_files:
        filename = os.path.basename(filepath)
        meta = DocumentMetadata(enterprise="Unknown", source_filename=filename, source_format="md")
        
        try:
            doc = parse_markdown_to_normalized(filepath, f"doc_{filename}", meta)
            
            for section in doc.sections:
                for block in section.blocks:
                    if block.block_type == "table":
                        total_tables += 1
                        is_sus, reasons = is_suspicious_table(block)
                        
                        if is_sus:
                            suspicious_tables += 1
                            hierarchy = " > ".join(section.hierarchy) if section.hierarchy else "Root"
                            
                            print(f"\n[SUSPICIOUS TABLE] File: {filename}")
                            print(f"Section: {hierarchy}")
                            print(f"Reasons: {', '.join(reasons)}")
                            print(f"Headers: {block.headers}")
                            if block.rows:
                                print(f"Row 1  : {block.rows[0]}")
                            print("-" * 50)
                            
        except Exception as e:
            pass # Ignoring parser errors here since validation already confirmed 100% success

    print(f"\nDiagnostic Complete.")
    print(f"Total tables analyzed: {total_tables}")
    print(f"Suspicious tables flagged: {suspicious_tables}")

if __name__ == "__main__":
    DATASET_PATH = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main" 
    run_table_diagnostic(DATASET_PATH)