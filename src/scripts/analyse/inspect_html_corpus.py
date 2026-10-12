import os
import glob
from collections import Counter, defaultdict
from bs4 import BeautifulSoup

def inspect_html_corpus(dataset_root: str):
    search_pattern = os.path.join(dataset_root, "datasets", "*", "html", "*.html")
    html_files = glob.glob(search_pattern)

    stats = {
        "total_files": len(html_files),
        "tag_counts": Counter(),
        "table_structures": {"with_thead": 0, "without_thead": 0, "with_tbody": 0, "total_tables": 0},
        "structural_tags": Counter(), # nav, header, footer, aside
        "files_missing_body": 0,
        "enterprise_distribution": Counter()
    }
    
    enterprise_examples = defaultdict(list)

    print("Analyzing HTML Corpus... This may take a few seconds.\n" + "="*50)

    for filepath in html_files:
        parts = filepath.replace("\\", "/").split("/")
        enterprise = parts[-3] if len(parts) >= 3 else "Unknown"
        filename = parts[-1]
        
        stats["enterprise_distribution"][enterprise] += 1
        if len(enterprise_examples[enterprise]) < 2:
            enterprise_examples[enterprise].append(filename)

        with open(filepath, 'r', encoding='utf-8') as f:
            # Using html.parser to see how standard Python handles it without external dependencies like lxml
            soup = BeautifulSoup(f, 'html.parser')
            
        if not soup.find('body'):
            stats["files_missing_body"] += 1

        # Count all tags
        for tag in soup.find_all(True):
            tag_name = tag.name
            stats["tag_counts"][tag_name] += 1
            
            # Check table structures specifically
            if tag_name == 'table':
                stats["table_structures"]["total_tables"] += 1
                if tag.find('thead'):
                    stats["table_structures"]["with_thead"] += 1
                else:
                    stats["table_structures"]["without_thead"] += 1
                if tag.find('tbody'):
                    stats["table_structures"]["with_tbody"] += 1
                    
            # Check for layout/junk elements
            if tag_name in ['nav', 'footer', 'header', 'aside']:
                stats["structural_tags"][tag_name] += 1

    # --- Print Report ---
    print(f"1. Total HTML files: {stats['total_files']}")
    print(f"   Files missing <body> tag: {stats['files_missing_body']}\n")
    
    print("2. Commonly Used Content Elements (Total Occurrences):")
    target_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'div', 'span', 'a']
    for tag in target_tags:
        print(f"   <{tag}>: {stats['tag_counts'][tag]}")
        
    print("\n3 & 4. Table Structures:")
    print(f"   Total HTML tables: {stats['table_structures']['total_tables']}")
    print(f"   Tables WITH <thead>: {stats['table_structures']['with_thead']}")
    print(f"   Tables WITHOUT <thead>: {stats['table_structures']['without_thead']}")
    print(f"   Tables with <tbody>: {stats['table_structures']['with_tbody']}")
    print(f"   Total <tr> rows: {stats['tag_counts']['tr']}")
    print(f"   Total <th> / <td>: {stats['tag_counts']['th']} / {stats['tag_counts']['td']}\n")
    
    print("5. Heading Consistency:")
    print(f"   Total Headings (h1-h6): {sum(stats['tag_counts'][f'h{i}'] for i in range(1, 7))}")
    print(f"   h1: {stats['tag_counts']['h1']} | h2: {stats['tag_counts']['h2']} | h3: {stats['tag_counts']['h3']}")
    
    print("\n6. Navigation & Layout Elements (Potential noise):")
    for tag in ['header', 'footer', 'nav', 'aside']:
        print(f"   <{tag}>: {stats['structural_tags'][tag]}")
        
    print("\n7. Links:")
    print(f"   Total <a> tags: {stats['tag_counts']['a']}\n")
    
    print("8 & 10. Enterprise Distribution & Examples:")
    for ent, count in stats["enterprise_distribution"].items():
        print(f"   {ent}: {count} files")
        print(f"      Examples: {', '.join(enterprise_examples[ent])}")

if __name__ == "__main__":
    DATASET_PATH = "Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main" 
    inspect_html_corpus(DATASET_PATH)