import os
import sys
import glob
import re
from bs4 import BeautifulSoup

def is_numbered(text):
    return bool(re.search(r'^\s*\d+[\.\)]\s', text))

def is_bulleted(text):
    return bool(re.search(r'^\s*[-•*]\s', text))

def is_heading_like(text):
    # Detects explicit markdown headers or short, heavily formatted title-like strings
    return bool(re.search(r'^\s*#+', text)) or (0 < len(text.strip()) < 60 and not is_numbered(text))

def run_analysis():
    # 1. Use the exact provided path
    corpus_dir = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets"
    
    # 2. Resolve to an absolute path
    abs_corpus_dir = os.path.abspath(corpus_dir)
    
    # 3. Print validation details
    print(f"Resolved corpus path: {abs_corpus_dir}")
    path_exists = os.path.exists(abs_corpus_dir)
    print(f"Path exists: {path_exists}")
    
    # 4. Stop execution if the path does not exist
    if not path_exists:
        print("\n[ERROR] Corpus directory does not exist. Please check your path and try again.")
        sys.exit(1)
        
    html_files = glob.glob(os.path.join(abs_corpus_dir, "**", "*.html"), recursive=True)
    print(f"Total HTML files found: {len(html_files)}")
    print("-" * 50)
    
    total_tables = 0
    suspicious_tables = []
    summary = {
        "has_thead": 0,
        "has_th": 0,
        "1_col_no_headers": 0,
    }

    print("Analyzing corpus tables...")

    for filepath in html_files:
        filename = os.path.basename(filepath)
        enterprise = os.path.basename(os.path.dirname(filepath)) 
        
        with open(filepath, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
            
        tables = soup.find_all('table')
        for table_idx, table in enumerate(tables):
            total_tables += 1
            
            rows = table.find_all('tr')
            if not rows:
                continue
                
            has_thead = table.find('thead') is not None
            has_th = table.find('th') is not None
            
            # Check column counts for data rows
            cols_per_row = [len(r.find_all(['td', 'th'], recursive=False)) for r in rows]
            if not cols_per_row:
                continue
                
            is_all_one_column = all(c == 1 for c in cols_per_row)
            
            if has_thead: summary["has_thead"] += 1
            if has_th: summary["has_th"] += 1
            
            # Extract sample text for heuristic evaluation
            row_texts = []
            for r in rows:
                cells = r.find_all(['td', 'th'])
                row_texts.append(" | ".join(c.get_text(separator=" ", strip=True) for c in cells))
            
            sample_rows = row_texts[:5]
            first_row = row_texts[0] if row_texts else ""
            
            numbered = any(is_numbered(r) for r in row_texts)
            bulleted = any(is_bulleted(r) for r in row_texts)
            heading_like = is_heading_like(first_row)
            
            # Cast a wide net for "suspicious" candidates: 1 column and lacks normal header markup
            if is_all_one_column and not has_thead and not has_th:
                summary["1_col_no_headers"] += 1
                
                suspicious_tables.append({
                    "filename": filename,
                    "enterprise": enterprise,
                    "num_rows": len(rows),
                    "numbered": numbered,
                    "bulleted": bulleted,
                    "heading_like_first": heading_like,
                    "samples": sample_rows
                })

    print("=" * 50)
    print(f"Total tables analyzed: {total_tables}")
    print("Summary Statistics:")
    print(f" - Tables with <thead>: {summary['has_thead']}")
    print(f" - Tables with explicit <th>: {summary['has_th']}")
    print(f" - 1-column tables with NO headers (Candidates): {summary['1_col_no_headers']}")
    print("=" * 50)
    
    print("\n--- SUSPICIOUS CANDIDATES ---")
    for st in suspicious_tables:
        print(f"\nFile: {st['filename']} (Enterprise: {st['enterprise']})")
        print(f"Rows: {st['num_rows']} | Numbered: {st['numbered']} | Bulleted: {st['bulleted']} | Heading-like 1st row: {st['heading_like_first']}")
        print("Sample Rows:")
        for i, r in enumerate(st['samples']):
            print(f"  [{i}] {r}")

if __name__ == '__main__':
    run_analysis()