import os
import glob
from bs4 import BeautifulSoup

def inspect_edge_cases(dataset_root: str):
    search_pattern = os.path.join(dataset_root, "datasets", "*", "html", "*.html")
    html_files = glob.glob(search_pattern)

    missing_thead_file = None
    missing_thead_html = None
    
    list_stats = {
        "total_lists": 0,
        "nested_lists": 0,  # lists inside other lists
        "li_with_p": 0,     # <li> containing <p>
        "li_with_strong": 0,# <li> containing <strong>/<b>
        "li_with_a": 0,     # <li> containing <a>
    }
    
    list_examples = []

    for filepath in html_files:
        filename = os.path.basename(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
            
        # 1. Investigate the 1 table without <thead>
        for table in soup.find_all('table'):
            if not table.find('thead') and missing_thead_html is None:
                missing_thead_file = filename
                missing_thead_html = table.prettify()
                
        # 2. Investigate list complexity
        for lst in soup.find_all(['ul', 'ol']):
            list_stats["total_lists"] += 1
            
            if lst.find_parent(['ul', 'ol']):
                list_stats["nested_lists"] += 1
                
            has_p = has_strong = has_a = False
            
            for li in lst.find_all('li', recursive=False):
                if li.find('p'): has_p = True
                if li.find(['strong', 'b']): has_strong = True
                if li.find('a'): has_a = True

            if has_p: list_stats["li_with_p"] += 1
            if has_strong: list_stats["li_with_strong"] += 1
            if has_a: list_stats["li_with_a"] += 1
            
            # Grab a few diverse examples to look at
            if len(list_examples) < 3 and (has_p or has_strong or list_stats["nested_lists"] > 0):
                # Only keep a snippet if it's huge
                snippet = str(lst)
                if len(snippet) > 300:
                    snippet = snippet[:300] + "\n  ... [TRUNCATED] ..."
                list_examples.append((filename, snippet))

    print("=== 1. TABLE WITHOUT <thead> ===")
    if missing_thead_file:
        print(f"File: {missing_thead_file}")
        print(missing_thead_html)
    else:
        print("Could not locate a table missing <thead>.")
        
    print("\n=== 2. LIST COMPLEXITY STATS ===")
    for key, val in list_stats.items():
        print(f"{key}: {val}")
        
    print("\n=== 3. REPRESENTATIVE LIST EXAMPLES ===")
    for idx, (fname, html_snippet) in enumerate(list_examples, 1):
        print(f"\n--- Example {idx} ({fname}) ---")
        print(html_snippet)

if __name__ == "__main__":
    DATASET_PATH = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main" 
    inspect_edge_cases(DATASET_PATH)