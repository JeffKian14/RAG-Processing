import os
import glob
from src.schemas import DocumentMetadata
from src.parsers.markdown_parser import parse_markdown_to_normalized

def run_validation(dataset_root: str):
    search_pattern = os.path.join(dataset_root, "datasets", "*", "md", "*.md")
    md_files = glob.glob(search_pattern)

    stats = {
        "total_files": len(md_files),
        "success": 0,
        "failed": 0,
        "docs_zero_sections": 0,
        "docs_zero_blocks": 0,
        "docs_with_tables": 0,
        "total_tables": 0,
        "total_text_blocks": 0,
        "max_depth": 0,
        "docs_with_h4": 0,
        "docs_with_h5": 0,
        "docs_with_h6": 0,
        "empty_text_blocks": 0,
        "malformed_tables": 0
    }
    
    exceptions = []

    for filepath in md_files:
        parts = filepath.replace("\\", "/").split("/")
        enterprise = parts[-3] if len(parts) >= 3 else "Unknown"
        filename = parts[-1]
        
        meta = DocumentMetadata(
            enterprise=enterprise, 
            source_filename=filename, 
            source_format="md"
        )
        
        try:
            doc = parse_markdown_to_normalized(filepath, f"doc_{filename}", meta)
            stats["success"] += 1
            
            if not doc.sections:
                stats["docs_zero_sections"] += 1
            
            doc_has_table = False
            doc_block_count = 0
            has_h4 = has_h5 = has_h6 = False
            
            for sec in doc.sections:
                depth = len(sec.hierarchy)
                stats["max_depth"] = max(stats["max_depth"], depth)
                
                if depth >= 4: has_h4 = True
                if depth >= 5: has_h5 = True
                if depth >= 6: has_h6 = True
                
                doc_block_count += len(sec.blocks)
                
                for block in sec.blocks:
                    if block.block_type == "text":
                        stats["total_text_blocks"] += 1
                        if not block.text.strip():
                            stats["empty_text_blocks"] += 1
                            
                    elif block.block_type == "table":
                        stats["total_tables"] += 1
                        doc_has_table = True
                        
                        # Malformed check: missing headers or row length mismatch
                        if not block.headers or any(len(row) != len(block.headers) for row in block.rows):
                            stats["malformed_tables"] += 1
            
            if doc_block_count == 0:
                stats["docs_zero_blocks"] += 1
            if doc_has_table:
                stats["docs_with_tables"] += 1
                
            if has_h4: stats["docs_with_h4"] += 1
            if has_h5: stats["docs_with_h5"] += 1
            if has_h6: stats["docs_with_h6"] += 1
            
        except Exception as e:
            stats["failed"] += 1
            exceptions.append((filename, str(e)))

    # --- Print Report ---
    print(f"Total files: {stats['total_files']}\n")
    print(f"Successfully parsed: {stats['success']}")
    print(f"Failed: {stats['failed']}\n")
    
    print(f"Documents with 0 sections: {stats['docs_zero_sections']}")
    print(f"Documents with 0 blocks: {stats['docs_zero_blocks']}")
    print(f"Documents containing tables: {stats['docs_with_tables']}")
    print(f"Total tables: {stats['total_tables']}")
    print(f"Total text blocks: {stats['total_text_blocks']}\n")
    
    print(f"Maximum hierarchy depth: {stats['max_depth']}")
    print(f"Documents with H4: {stats['docs_with_h4']}")
    print(f"Documents with H5: {stats['docs_with_h5']}")
    print(f"Documents with H6: {stats['docs_with_h6']}\n")
    
    print(f"Empty text blocks: {stats['empty_text_blocks']}")
    print(f"Malformed tables: {stats['malformed_tables']}\n")
    
    if exceptions:
        print("Parser exceptions\n-----------------")
        for filename, error in exceptions:
            print(f"{filename} -> {error}")

if __name__ == "__main__":
    DATASET_PATH = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main" 
    run_validation(DATASET_PATH)