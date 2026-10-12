import os
import glob
import pymupdf
import re
from collections import Counter, defaultdict

def run_layout_analysis():
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)
    
    if not pdf_files:
        print("No PDF files found.")
        return

    print(f"Starting revised layout analysis on {len(pdf_files)} PDFs...")

    # Metrics
    total_pages = 0
    font_sizes = Counter()
    font_names = Counter()
    bold_font_sizes = Counter()
    counts = {"spans": 0, "lines": 0, "blocks": 0}
    list_indicators = Counter()
    hyphenations = []
    
    # Structure metrics
    page_number_candidates = defaultdict(list)
    edge_text_tracker = defaultdict(Counter)
    table_candidates = []

    for filepath in pdf_files:
        filename = os.path.basename(filepath)
        try:
            doc = pymupdf.open(filepath)
            total_pages += len(doc)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_height = page.rect.height
                dict_data = page.get_text("dict")
                
                # Table detection: track x0s grouped by approximate y0 (rows)
                row_x0s = defaultdict(list)
                
                for block in dict_data.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    counts["blocks"] += 1
                    
                    for line in block.get("lines", []):
                        counts["lines"] += 1
                        line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                        
                        # Hyphenation check
                        if line_text.endswith("-") and len(line_text) > 3:
                            if len(hyphenations) < 15:
                                hyphenations.append(f"{filename} (p{page_num+1}): '{line_text}'")
                        
                        # List indicators check
                        list_match = re.match(r'^([•\-\*]|\d+\.)\s', line_text)
                        if list_match:
                            list_indicators[list_match.group(1)] += 1
                            
                        # Process spans
                        for span in line.get("spans", []):
                            counts["spans"] += 1
                            text = span.get("text", "").strip()
                            if not text:
                                continue
                                
                            size = round(span.get("size", 0), 1)
                            font = span.get("font", "Unknown")
                            flags = span.get("flags", 0)
                            is_bold = "bold" in font.lower() or bool(flags & 2**4)
                            
                            bbox = span.get("bbox", [0,0,0,0])
                            x0, y0, x1, y1 = bbox
                            
                            font_sizes[size] += 1
                            font_names[font] += 1
                            if is_bold:
                                bold_font_sizes[size] += 1
                                
                            # Table layout gathering: group by y0 rounded to nearest 5
                            row_y = round(y0 / 5) * 5
                            row_x0s[row_y].append(round(x0 / 5) * 5)
                            
                            # Edge text (Top 10% or Bottom 10%)
                            if y0 < page_height * 0.10 or y1 > page_height * 0.90:
                                norm_text = re.sub(r'\s+', ' ', text)
                                if len(norm_text) > 4 and not norm_text.isdigit():
                                    edge_text_tracker[filename][norm_text] += 1
                                    
                            # Page numbers (Bottom 15%, short numeric text)
                            if y1 > page_height * 0.85 and text.isdigit() and len(text) <= 3:
                                page_number_candidates[filename].append({
                                    "page": page_num + 1,
                                    "text": text,
                                    "y": round(y1, 1),
                                    "bbox": [round(c, 1) for c in bbox]
                                })

                # Analyze table candidates on this page
                # We look for rows that have more than 1 column, and see if those column x0s repeat
                col_freq = Counter()
                multi_col_rows = 0
                for r_y, x0_list in row_x0s.items():
                    unique_x0s = list(set(x0_list))
                    if len(unique_x0s) >= 2:  # Row has at least 2 distinct text chunks
                        multi_col_rows += 1
                        for x in unique_x0s:
                            col_freq[x] += 1
                            
                # If we have at least 3 rows sharing at least 2 common column starting positions
                stable_columns = [x for x, count in col_freq.items() if count >= 3]
                if len(stable_columns) >= 2 and multi_col_rows >= 3:
                    if len(table_candidates) < 15:
                        table_candidates.append(f"{filename} (p{page_num+1}) - {len(stable_columns)} stable columns over {multi_col_rows} rows")

            doc.close()
        except Exception as e:
            pass

    # --- Generate Report ---
    print("\nPDF LAYOUT ANALYSIS")
    print("====================")
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Total pages: {total_pages}\n")
    
    print("TEXT SPANS")
    print(f"Total text blocks: {counts['blocks']}")
    print(f"Total lines: {counts['lines']}")
    print(f"Total spans: {counts['spans']}\n")

    print("FONT SIZES (Top 3)")
    for size, count in font_sizes.most_common(3):
        print(f"  {size} pt: {count} spans")
        
    print("\nBOLD FONT SIZES (Top 3)")
    for size, count in bold_font_sizes.most_common(3):
        print(f"  {size} pt: {count} spans")

    print("\nPAGE NUMBER ANALYSIS")
    valid_seq_count = 0
    print(f"Pages with numeric candidates: {sum(len(cands) for cands in page_number_candidates.values())}")
    
    print("Examples of sequential candidates:")
    sample_count = 0
    for filename, cands in page_number_candidates.items():
        if len(cands) >= 2:
            # Check if they are actually sequential (e.g., '1', '2')
            if int(cands[0]['text']) + 1 == int(cands[1]['text']):
                valid_seq_count += 1
                if sample_count < 3:
                    print(f"  File: {filename}")
                    print(f"  - PDF p{cands[0]['page']} -> Text: '{cands[0]['text']}' | y={cands[0]['y']} | bbox={cands[0]['bbox']}")
                    print(f"  - PDF p{cands[1]['page']} -> Text: '{cands[1]['text']}' | y={cands[1]['y']} | bbox={cands[1]['bbox']}")
                    sample_count += 1
    print(f"PDFs with likely sequential page numbers: {valid_seq_count}")

    print("\nREPEATED EDGE TEXT CANDIDATES (Headers/Footers)")
    edge_examples = 0
    for filename, text_counts in edge_text_tracker.items():
        for text, count in text_counts.items():
            if count >= 3:  # Appears on at least 3 pages
                if edge_examples < 5:
                    print(f"  {filename}: '{text}' (Appears on {count} pages)")
                    edge_examples += 1

    print(f"\nTABLE-LIKE LAYOUT DETECTION")
    print(f"Pages matching columnar structure criteria: {len(table_candidates)}")
    for ex in table_candidates[:5]:
        print(f"  - {ex}")

if __name__ == '__main__':
    run_layout_analysis()