import os
import glob
import copy
from src.parsers.pdf_parser import (
    PDFSpan, PDFLine, ReconstructedTextUnit, 
    parse_pdf_to_lines, repair_hyphenation, filter_edge_noise
)

def create_mock_unit(text: str, y0: float, y1: float, page_num: int, page_height: float = 800.0) -> ReconstructedTextUnit:
    """Helper to generate a mock ReconstructedTextUnit using formal constructors."""
    # Note: 15% of 800 is 120 (Top edge: y < 120, Bottom edge: y > 680)
    span = PDFSpan(
        text=text, page_number=page_num, block_idx=0, line_idx=0,
        x0=50.0, y0=y0, x1=100.0, y1=y1,
        font="Helv", size=10.0, is_bold=False, is_italic=False
    )
    
    # Constructing PDFLine formally using the new page_width and page_height parameters
    line = PDFLine(
        spans=[span], 
        page_number=page_num, 
        block_idx=0, 
        line_idx=0,
        page_width=600.0,
        page_height=page_height
    )
    
    return ReconstructedTextUnit(text=text, source_lines=[line])

def run_synthetic_tests():
    print("======================================================================")
    print("STEP 6E-6: EDGE NOISE FILTERING (SYNTHETIC)")
    print("======================================================================\n")

    # Constructing the required test cases
    units = [
        # 1. Bottom standalone page numbers (y0=750)
        create_mock_unit("1", 750.0, 760.0, page_num=1),
        create_mock_unit("2", 750.0, 760.0, page_num=2),
        
        # 2. Top standalone page numbers (y0=30)
        create_mock_unit("Page 3", 30.0, 40.0, page_num=3),
        create_mock_unit("Page 4", 30.0, 40.0, page_num=4),

        # 3. Repeated top 'Internal Use Only' (y0=30)
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=1),
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=2),
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=3),

        # 4. Repeated footer (y0=770)
        create_mock_unit("Confidential", 770.0, 780.0, page_num=1),
        create_mock_unit("Confidential", 770.0, 780.0, page_num=2),
        create_mock_unit("Confidential", 770.0, 780.0, page_num=3),

        # 5. Body number 1 (y0=400)
        create_mock_unit("1", 400.0, 410.0, page_num=1),

        # 6. Body number 2024 (y0=400)
        create_mock_unit("2024", 400.0, 410.0, page_num=1),

        # 7. Repeated body text (y0=400)
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=1),
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=2),
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=3),

        # 8. One-page title (y0=30, single page)
        create_mock_unit("Main Title", 30.0, 40.0, page_num=1),

        # 9. Non-repeated top headings (y0=40, single pages)
        create_mock_unit("Chapter 1", 40.0, 50.0, page_num=1),
        create_mock_unit("Chapter 2", 40.0, 50.0, page_num=2),

        # 10. Different headers on different pages
        create_mock_unit("Header A", 30.0, 40.0, page_num=1),
        create_mock_unit("Header B", 30.0, 40.0, page_num=2),
        create_mock_unit("Header C", 30.0, 40.0, page_num=3),
    ]

    # Deepcopy to test immutability
    original_units_state = copy.deepcopy(units)
    
    result = filter_edge_noise(units)
    
    filtered_reasons = {f.unit.text: f.reason for f in result.filtered_units}
    kept_texts = [u.text for u in result.kept_units]

    # Required Assertions
    assert filtered_reasons.get("1") == "page_number"
    print("[PASS] Bottom standalone page numbers -> FILTERED (page_number)")
    
    assert filtered_reasons.get("Page 3") == "page_number"
    print("[PASS] Top standalone page numbers -> FILTERED (page_number)")

    assert filtered_reasons.get("Internal Use Only") == "repeated_header"
    print("[PASS] Repeated top 'Internal Use Only' -> FILTERED (repeated_header)")

    assert filtered_reasons.get("Confidential") == "repeated_footer"
    print("[PASS] Repeated footer -> FILTERED (repeated_footer)")

    assert kept_texts.count("1") == 1 # The body number
    print("[PASS] Body number '1' -> PRESERVED")

    assert "2024" in kept_texts
    print("[PASS] Body number '2024' -> PRESERVED")

    assert kept_texts.count("Internal Use Only") == 3 # The 3 body instances
    print("[PASS] Repeated body text -> PRESERVED")

    assert "Main Title" in kept_texts
    print("[PASS] One-page title -> PRESERVED")

    assert "Chapter 1" in kept_texts and "Chapter 2" in kept_texts
    print("[PASS] Non-repeated top headings -> PRESERVED")

    assert "Header A" in kept_texts and "Header B" in kept_texts
    print("[PASS] Different headers on different pages -> PRESERVED")

    # 11, 12, 13: Immutability Checks
    for original, current in zip(original_units_state, units):
        assert original.text == current.text
        assert len(original.source_lines) == len(current.source_lines)
        assert original.source_lines[0].page_height == current.source_lines[0].page_height
        assert original.source_lines[0].spans[0].y0 == current.source_lines[0].spans[0].y0
        assert original.source_lines[0].spans[0].text == current.source_lines[0].spans[0].text

    print("[PASS] Original ReconstructedTextUnit remains unchanged -> CONFIRMED")
    print("[PASS] Original PDFLine remains unchanged -> CONFIRMED")
    print("[PASS] Original PDFSpan remains unchanged -> CONFIRMED\n")

def run_real_corpus_test():
    print("======================================================================")
    print("STEP 6E-6: REAL CORPUS VALIDATION")
    print("======================================================================\n")
    
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    if not os.path.exists(corpus_dir):
        corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi_Corpus-main/datasets")
        
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)

    targets = ["About Aventro Motors", "ZX_Bank_Policies", "Cendara_University_Courses"]
    
    for target in targets:
        target_pdf = next((f for f in pdf_files if target in f or target.replace("_", " ") in f), None)
        if not target_pdf:
            continue

        filename = os.path.basename(target_pdf)
        print(f"Document: {filename}")
        
        # Pipeline execution
        lines = parse_pdf_to_lines(target_pdf)
        units = repair_hyphenation(lines)
        result = filter_edge_noise(units)
        
        print(f"Total units: {len(units)}")
        print(f"Kept units: {len(result.kept_units)}")
        print(f"Filtered units: {len(result.filtered_units)}\n")

        p_nums = sum(1 for f in result.filtered_units if f.reason == "page_number")
        r_heads = sum(1 for f in result.filtered_units if f.reason == "repeated_header")
        r_foots = sum(1 for f in result.filtered_units if f.reason == "repeated_footer")

        print(f"Page numbers filtered: {p_nums}")
        print(f"Repeated headers filtered: {r_heads}")
        print(f"Repeated footers filtered: {r_foots}\n")
        
        print("FILTERED [page_number]")
        for f in [u for u in result.filtered_units if u.reason == "page_number"][:2]:
            print(f"  Page {f.unit.source_lines[0].page_number}: {f.unit.text!r}")
            
        print("\nFILTERED [repeated_header]")
        for f in [u for u in result.filtered_units if u.reason == "repeated_header"][:2]:
            print(f"  Page {f.unit.source_lines[0].page_number}: {f.unit.text!r}")
            
        print("\nPRESERVED EXAMPLES:")
        for u in result.kept_units[:3]:
            if len(u.text.strip()) > 1:
                desc = "(Body content)"
                y0 = min(line.bbox[1] for line in u.source_lines)
                if y0 < u.source_lines[0].page_height * 0.15:
                    desc = "(Top edge, non-repeating title)"
                
                print(f"  {u.text!r} {desc}")
        print("\n" + "-"*70 + "\n")

if __name__ == "__main__":
    run_synthetic_tests()
    run_real_corpus_test()