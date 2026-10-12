import os
import glob
from src.parsers.pdf_parser import parse_pdf_to_lines

def run_inspection():
    # Use the known working path
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus_dir):
        corpus_dir = os.path.abspath("Dataset/RAG-Multi_Corpus-main/RAG-Multi_Corpus-main/datasets")

    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)
    if not pdf_files:
        print("No PDF files found.")
        return

    # Identify one representative PDF for each target enterprise
    targets = {"ZX Bank": None, "Cendara University": None, "Aventro Motors": None}
    for f in pdf_files:
        for ent in targets.keys():
            # Match folder/filename heuristics
            if ent.lower() in f.lower() or ent.replace(" ", "_").lower() in f.lower():
                if targets[ent] is None:
                    targets[ent] = f

    selected_pdfs = [f for f in targets.values() if f]
    
    for pdf_path in selected_pdfs:
        filename = os.path.basename(pdf_path)
        print("=" * 80)
        print(f"INSPECTING: {filename}")
        print("=" * 80)
        
        try:
            # REAL PARSER CALL
            lines = parse_pdf_to_lines(pdf_path)
            
            total_lines = len(lines)
            tab_lines = sum(1 for l in lines if '\t' in l.text)
            hyphen_lines = sum(1 for l in lines if l.text.strip().endswith('-'))
            short_lines = sum(1 for l in lines if len(l.text.strip()) <= 2 and l.text.strip().isalpha())
            
            print("--- SUMMARY STATISTICS ---")
            print(f"Total PDFLine objects: {total_lines}")
            print(f"Lines containing \\t (column gaps): {tab_lines}")
            print(f"Lines ending in '-': {hyphen_lines}")
            print(f"Suspiciously short lines (<= 2 chars): {short_lines}")
            print("--------------------------\n")
            
            print("--- FIRST 40 RECONSTRUCTED LINES ---")
            for line in lines[:40]:
                print(f"[P{line.page_number} B{line.block_idx:02d} L{line.line_idx:02d}] {line.text!r}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    run_inspection()
