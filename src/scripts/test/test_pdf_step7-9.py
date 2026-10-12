import os
import glob
from src.parsers.pdf_parser import convert_pdf_to_normalized_document
from src.schemas import TextBlock, TableBlock, ListBlock, ImageBlock

def print_doc_summary(doc):
    print(f"Document: {doc.metadata.source_filename}")
    print(f"Title: {doc.title}")
    print(f"Enterprise: {doc.metadata.enterprise}")
    
    t_blocks = sum(sum(1 for b in s.blocks if isinstance(b, TextBlock)) for s in doc.sections)
    l_blocks = sum(sum(1 for b in s.blocks if isinstance(b, ListBlock)) for s in doc.sections)
    tbl_blocks = sum(sum(1 for b in s.blocks if isinstance(b, TableBlock)) for s in doc.sections)
    img_blocks = sum(sum(1 for b in s.blocks if isinstance(b, ImageBlock)) for s in doc.sections)
    
    print(f"Sections: {len(doc.sections)}")
    print(f"TextBlocks: {t_blocks}")
    print(f"ListBlocks: {l_blocks}")
    print(f"TableBlocks: {tbl_blocks}")
    print(f"ImageBlocks: {img_blocks}\n")

    for i, section in enumerate(doc.sections[:2]):
        print(f"  Hierarchy: {section.hierarchy}")
        print("  Blocks:")
        for block in section.blocks[:3]:
            if isinstance(block, TextBlock):
                print(f"    TextBlock: {block.text[:50]}...")
            elif isinstance(block, ListBlock):
                print(f"    ListBlock ({block.list_type}, {len(block.items)} root items)")
            elif isinstance(block, TableBlock):
                print(f"    TableBlock ({len(block.headers)} cols, {len(block.rows)} rows)")
            elif isinstance(block, ImageBlock):
                print(f"    ImageBlock (Page {block.page_number})")
        if len(section.blocks) > 3:
            print("    ...")
        print("")

def run_tests():
    print("======================================================================")
    print("STEP 6F: NORMALIZED DOCUMENT CONVERSION")
    print("======================================================================\n")

    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus_dir):
        corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi_Corpus-main/datasets")
        
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)
    
    targets = ["About Aventro Motors", "academic_calendar", "(UPI) – ZX Bank Asia"]
    for target in targets:
        pdf_path = next((f for f in pdf_files if target.lower() in os.path.basename(f).lower()), None)
        if not pdf_path:
            token = target.split()[0].replace("(", "")
            pdf_path = next((f for f in pdf_files if token.lower() in os.path.basename(f).lower()), None)
        
        if pdf_path:
            doc = convert_pdf_to_normalized_document(pdf_path)
            print_doc_summary(doc)

    print("\n======================================================================")
    print("MASS VALIDATION (ALL 236 PDFs)")
    print("======================================================================")
    
    success, failed = 0, 0
    for pdf in pdf_files:
        try:
            doc = convert_pdf_to_normalized_document(pdf)
            # Implicit Pydantic validation on schema build
            _ = doc.model_dump()
            success += 1
        except Exception as e:
            failed += 1
            print(f"Failed on {os.path.basename(pdf)}: {e}")
            
    print(f"\nTotal PDFs: {len(pdf_files)}")
    print(f"Successfully normalized: {success}")
    print(f"Failed: {failed}")

if __name__ == "__main__":
    run_tests()