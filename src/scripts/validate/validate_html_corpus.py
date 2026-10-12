import os
import glob
from bs4 import BeautifulSoup
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_validation():
    corpus_dir = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets"
    abs_corpus_dir = os.path.abspath(corpus_dir)
    html_files = glob.glob(os.path.join(abs_corpus_dir, "**", "*.html"), recursive=True)
    
    metrics = {
        "total_files": len(html_files),
        "success": 0,
        "failed": 0,
        "zero_sections": 0,
        "zero_blocks": 0,
        "text_blocks": 0,
        "list_blocks": 0,
        "table_blocks": 0,
        "image_blocks": 0,
        "pseudo_tables": 0
    }
    
    print("Running full HTML corpus validation...")
    
    for filepath in html_files:
        filename = os.path.basename(filepath)
        enterprise = os.path.basename(os.path.dirname(filepath))
        meta = DocumentMetadata(enterprise=enterprise, source_filename=filename, source_format="html")
        
        try:
            # Quick raw count to detect conversions
            with open(filepath, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            raw_table_count = len(soup.find_all('table'))
            
            doc = parse_html_to_normalized(filepath, filename, meta)
            metrics["success"] += 1
            
            if not doc.sections:
                metrics["zero_sections"] += 1
            
            doc_block_count = 0
            doc_table_blocks = 0
            
            for sec in doc.sections:
                doc_block_count += len(sec.blocks)
                for block in sec.blocks:
                    if block.block_type == 'text': 
                        metrics["text_blocks"] += 1
                    elif block.block_type == 'list': 
                        metrics["list_blocks"] += 1
                    elif block.block_type == 'table': 
                        metrics["table_blocks"] += 1
                        doc_table_blocks += 1
                    elif block.block_type == 'image': 
                        metrics["image_blocks"] += 1
                    
            if doc_block_count == 0:
                metrics["zero_blocks"] += 1
                
            # The difference between raw tables and TableBlocks is the number of pseudo-table conversions
            metrics["pseudo_tables"] += (raw_table_count - doc_table_blocks)
            
        except Exception as e:
            metrics["failed"] += 1
            print(f"Failed parsing {filename}: {e}")

    print("="*50)
    print("HTML CORPUS VALIDATION RESULTS")
    print("="*50)
    print(f"Total HTML files: {metrics['total_files']}")
    print(f"Successfully parsed: {metrics['success']}")
    print(f"Failed: {metrics['failed']}")
    print(f"Documents with 0 sections: {metrics['zero_sections']}")
    print(f"Documents with 0 blocks: {metrics['zero_blocks']}")
    print("-" * 50)
    print(f"Total TextBlocks: {metrics['text_blocks']}")
    print(f"Total ListBlocks: {metrics['list_blocks']}")
    print(f"Total TableBlocks: {metrics['table_blocks']}")
    print(f"Total ImageBlocks: {metrics['image_blocks']}")
    print("-" * 50)
    print(f"Pseudo-table conversions: {metrics['pseudo_tables']}")
    print("="*50)

if __name__ == '__main__':
    run_validation()