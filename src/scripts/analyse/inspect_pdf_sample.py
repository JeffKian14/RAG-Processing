import os
import glob
import pymupdf

def run_inspection():
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)
    
    if not pdf_files:
        print("No PDF files found.")
        return

    print("=" * 80)
    print("1. DIRECTORY STRUCTURE CHECK (First 3 PDFs)")
    for f in pdf_files[:3]:
        print(f"   {os.path.relpath(f, corpus_dir)}")
    print("=" * 80)

    # 2. Identify enterprises by content rather than folder
    known_enterprises = [
        "Aventro Motors", 
        "Cendara University", 
        "CloudWay-24", 
        "Velvera Technologies", 
        "ZX Bank"
    ]
    
    enterprise_candidates = {e: [] for e in known_enterprises}
    
    print("\nScanning PDFs to identify enterprises by content...")
    for filepath in pdf_files:
        try:
            doc = pymupdf.open(filepath)
            # Scan just the first page to assign an enterprise
            first_page_text = doc[0].get_text("text").strip()
            
            for ent in known_enterprises:
                if ent.lower() in first_page_text.lower():
                    enterprise_candidates[ent].append((filepath, len(doc)))
                    break  # Assign to first match and move on
            doc.close()
        except Exception:
            pass

    # 3. Select the largest PDF from each enterprise
    selected_pdfs = []
    for ent, files in enterprise_candidates.items():
        if files:
            # Sort by page count descending
            files.sort(key=lambda x: x[1], reverse=True)
            selected_pdfs.append((ent, files[0][0]))

    print(f"\nSelected {len(selected_pdfs)} representative PDFs.\n")

    # 4. Deep Inspection
    for ent, filepath in selected_pdfs:
        filename = os.path.basename(filepath)
        print("=" * 80)
        print(f"ENTERPRISE: {ent} | FILE: {filename}")
        
        try:
            doc = pymupdf.open(filepath)
            print(f"Total Pages: {len(doc)}")
            print("-" * 80)
            
            # Inspect up to 5 pages to capture continuations, headers/footers, etc.
            pages_to_inspect = min(5, len(doc))
            
            for page_num in range(pages_to_inspect):
                page = doc[page_num]
                
                print(f"\n{'='*20} PAGE {page_num + 1} {'='*20}")
                
                # --- A. Plain Text Reading Order Check ---
                raw_text = page.get_text("text")
                print("--- RAW TEXT PREVIEW (Reading Order Check) ---")
                print(raw_text[:1500])
                if len(raw_text) > 1500:
                    print("\n... [TEXT TRUNCATED] ...")
                
                # --- B. Structural / Dict Check ---
                print("\n--- STRUCTURED DICT PREVIEW (Representative Spans) ---")
                dict_data = page.get_text("dict")
                blocks = dict_data.get("blocks", [])
                
                span_count = 0
                for b in blocks:
                    if b.get("type") == 0:  # Text block
                        # Grab just the first span of a block to get a cross-section of the page layout
                        lines = b.get("lines", [])
                        if lines:
                            spans = lines[0].get("spans", [])
                            if spans:
                                s = spans[0]
                                font_name = s.get('font', '')
                                size = s.get('size', 0)
                                text = s.get('text', '').strip()
                                bbox = s.get('bbox', [])
                                
                                # Basic bold/italic heuristic from font name/flags
                                flags = s.get('flags', 0)
                                is_bold = "bold" in font_name.lower() or bool(flags & 2**4)
                                is_italic = "italic" in font_name.lower() or bool(flags & 2**1)
                                
                                style_str = []
                                if is_bold: style_str.append("BOLD")
                                if is_italic: style_str.append("ITALIC")
                                style_display = f" [{','.join(style_str)}]" if style_str else ""
                                
                                if text:  # Only print non-empty spans
                                    # Format bbox to 1 decimal place for readability
                                    bbox_fmt = [round(coord, 1) for coord in bbox]
                                    print(f"Span: {text[:60]!r:<60} | Font: {size:4.1f}pt {font_name}{style_display} | BBox: {bbox_fmt}")
                                    span_count += 1
                                    
                    if span_count >= 8:  # 8 representative lines per page is enough to spot heading vs body differences
                        break
                        
            if len(doc) > 5:
                print(f"\n... Skipping remaining {len(doc) - 5} pages ...")
                
            doc.close()
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == '__main__':
    run_inspection()