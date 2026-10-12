import os
import glob
import fitz  # PyMuPDF

def run_pdf_analysis():
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)
    
    if not pdf_files:
        print(f"No PDF files found in {corpus_dir}")
        return

    metrics = {
        "total_files": len(pdf_files),
        "readable": 0,
        "failed": 0,
        "total_pages": 0,
        "pages_list": [],
        "total_text_len": 0,
        "no_text_pdfs": 0,
        "pdfs_with_tables": 0,
        "estimated_tables": 0,
        "pdfs_with_images": 0,
        "estimated_images": 0
    }

    print("Analyzing PDF corpus structure (this may take a moment)...")

    for filepath in pdf_files:
        filename = os.path.basename(filepath)
        
        try:
            doc = fitz.open(filepath)
            metrics["readable"] += 1
            
            num_pages = len(doc)
            metrics["total_pages"] += num_pages
            metrics["pages_list"].append(num_pages)
            
            doc_has_text = False
            doc_has_tables = False
            doc_has_images = False
            doc_text_len = 0
            
            for page in doc:
                # 1. Text extraction
                text = page.get_text("text")
                if text.strip():
                    doc_has_text = True
                    doc_text_len += len(text)
                
                # 2. Image detection
                images = page.get_images(full=True)
                if images:
                    doc_has_images = True
                    metrics["estimated_images"] += len(images)
                    
                # 3. Table detection (heuristic available in recent PyMuPDF versions)
                if hasattr(page, "find_tables"):
                    tables = page.find_tables()
                    if tables and tables.tables:
                        doc_has_tables = True
                        metrics["estimated_tables"] += len(tables.tables)
                        
            metrics["total_text_len"] += doc_text_len
            if not doc_has_text:
                metrics["no_text_pdfs"] += 1
            if doc_has_tables:
                metrics["pdfs_with_tables"] += 1
            if doc_has_images:
                metrics["pdfs_with_images"] += 1
                
            doc.close()
            
        except Exception as e:
            metrics["failed"] += 1
            print(f"Failed to read {filename}: {e}")

    # Calculate aggregates
    min_pages = min(metrics["pages_list"]) if metrics["pages_list"] else 0
    max_pages = max(metrics["pages_list"]) if metrics["pages_list"] else 0
    avg_pages = sum(metrics["pages_list"]) / len(metrics["pages_list"]) if metrics["pages_list"] else 0
    avg_text = metrics["total_text_len"] / metrics["readable"] if metrics["readable"] else 0

    print("\n" + "="*50)
    print("PDF CORPUS ANALYSIS")
    print("="*50)
    print(f"Total PDF files: {metrics['total_files']}\n")
    print(f"Readable PDFs: {metrics['readable']}")
    print(f"Failed PDFs: {metrics['failed']}\n")
    print(f"Total pages: {metrics['total_pages']}")
    print(f"Min pages: {min_pages}")
    print(f"Max pages: {max_pages}")
    print(f"Average pages: {avg_pages:.1f}\n")
    print(f"Total extracted text length: {metrics['total_text_len']} chars")
    print(f"PDFs with no extractable text: {metrics['no_text_pdfs']} (potential scans)")
    print(f"Average text length per PDF: {avg_text:.0f} chars\n")
    print(f"PDFs containing tables: {metrics['pdfs_with_tables']}")
    print(f"Estimated tables: {metrics['estimated_tables']}\n")
    print(f"PDFs containing images: {metrics['pdfs_with_images']}")
    print(f"Estimated images: {metrics['estimated_images']}")
    print("-" * 50)
    print("STRUCTURAL OBSERVATIONS")
    print("-" * 50)
    print("Note: If 'PDFs with no extractable text' > 0, OCR handling is required.")
    print("Note: If 'Estimated tables' > 0, layout-aware extraction (like PyMuPDF's find_tables or pdfplumber) is necessary.")
    print("Run complete. Awaiting supervisor review before proceeding to parser implementation.")

if __name__ == '__main__':
    run_pdf_analysis()