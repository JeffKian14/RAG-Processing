import os
import glob
from src.parsers.pdf_parser import (
    PDFSpan, PDFLine, ReconstructedTextUnit, 
    parse_pdf_to_lines, repair_hyphenation, filter_edge_noise
)

def create_mock_unit(text: str, y0: float, y1: float, page_num: int, page_height: float = 800.0):
    """Helper to generate a mock ReconstructedTextUnit for spatial testing."""
    # Note: 15% of 800 is 120 (Top edge: y < 120, Bottom edge: y > 680)
    span = PDFSpan(
        text=text, page_number=page_num, block_idx=0, line_idx=0,
        x0=50.0, y0=y0, x1=100.0, y1=y1,
        font="Helv", size=10.0, is_bold=False, is_italic=False
    )
    # Using setattr to handle the backward-compatible page_width/page_height addition
    object.__setattr__(span, 'page_width', 600.0)
    object.__setattr__(span, 'page_height', page_height)
    
    line = PDFLine(spans=[span], page_number=page_num, block_idx=0, line_idx=0)
    line.page_width = 600.0
    line.page_height = page_height
    
    return ReconstructedTextUnit(text=text, source_lines=[line])

def run_synthetic_tests():
    print("======================================================================")
    print("STEP 6E-6: EDGE NOISE FILTERING")
    print("======================================================================\n")
    print("--- SYNTHETIC TESTS ---")

    units = [
        # 1. Bottom standalone page numbers (y0=750, y1=760) -> DETECTED
        create_mock_unit("1", 750.0, 760.0, page_num=1),
        create_mock_unit("2", 750.0, 760.0, page_num=2),
        
        # 2. Repeated header (y0=30, y1=40) across 3 pages -> DETECTED
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=1),
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=2),
        create_mock_unit("Internal Use Only", 30.0, 40.0, page_num=3),

        # 3. Repeated footer (y0=770, y1=780) across 3 pages -> DETECTED
        create_mock_unit("Confidential", 770.0, 780.0, page_num=1),
        create_mock_unit("Confidential", 770.0, 780.0, page_num=2),
        create_mock_unit("Confidential", 770.0, 780.0, page_num=3),

        # 4. Body number '1' (y0=400, middle of page) -> PRESERVED
        create_mock_unit("1", 400.0, 410.0, page_num=1),

        # 5. Body repeated text (y0=400) -> PRESERVED
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=1),
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=2),
        create_mock_unit("Internal Use Only", 400.0, 410.0, page_num=3),

        # 6. One-page title (y0=30, only 1 page) -> PRESERVED
        create_mock_unit("Main Title", 30.0, 40.0, page_num=1)
    ]

    result = filter_edge_noise(units)
    filtered_reasons = {f.unit.text: f.reason for f in result.filtered_units}
    kept_texts = {u.text for u in result.kept_units}

    # Assertions
    assert filtered_reasons.get("1") == "page_number"
    assert filtered_reasons.get("2") == "page_number"
    print("✓ Bottom standalone page numbers detected -> FILTERED (page_number)")

    assert filtered_reasons.get("Internal Use Only") == "repeated_header"
    print("✓ Repeated header detected -> FILTERED (repeated_header)")

    assert filtered_reasons.get("Confidential") == "repeated_footer"
    print("✓ Repeated footer detected -> FILTERED (repeated_footer)")

    # The body "1" should be in kept_texts, but because texts are duplicated in the mock,
    # we verify by counting kept instances vs filtered instances.
    body_number_kept = any(u.text == "1" and u.source_lines[0].spans[0].y0 == 400.0 for u in result.kept_units)
    assert body_number_kept
    print("✓ Body number preserved -> PRESERVED")

    body_repeat_kept = any(u.text == "Internal Use Only" and u.source_lines[0].spans[0].y0 == 400.0 for u in result.kept_units)
    assert body_repeat_kept
    print("✓ Body repeated text preserved -> PRESERVED")

    assert "Main Title" in kept_texts
    print("✓ One-page title preserved -> PRESERVED\n")

def run_real_corpus_test():
    print("--- REAL CORPUS VALIDATION ---\n")
    corpus_dir = os.path.abspath("Dataset/RAG-Multi-Corpus-main/RAG-Multi-Corpus-main/datasets")
    pdf_files = glob.glob(os.path.join(corpus_dir, "**", "*.pdf"), recursive=True)

    targets = ["ZX_Bank_Policies", "About Aventro Motors", "Cendara_University_Courses"]
    
    for target in targets:
        target_pdf = next((f for f in pdf_files if target in f or target.replace("_", " ") in f), None)
        if not target_pdf:
            continue

        filename = os.path.basename(target_pdf)
        print(f"Document: {filename}")
        
        # 1. Parse lines
        lines = parse_pdf_to_lines(target_pdf)
        # 2. Repair Hyphenation (creates ReconstructedTextUnits)
        units = repair_hyphenation(lines)
        # 3. Filter Edge Noise
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
        
        print("FILTERED [page_number]:")
        for f in [u for u in result.filtered_units if u.reason == "page_number"][:2]:
            print(f"  Page {f.unit.source_lines[0].page_number}: {f.unit.text!r}")
            
        print("\nFILTERED [repeated_header]:")
        for f in [u for u in result.filtered_units if u.reason == "repeated_header"][:2]:
            print(f"  Page {f.unit.source_lines[0].page_number}: {f.unit.text!r}")
            
        print("\nPRESERVED:")
        for u in result.kept_units[:3]:
            # Just grab a few meaningful lines
            if len(u.text) > 5:
                print(f"  {u.text!r}")
        print("\n")

if __name__ == "__main__":
    run_synthetic_tests()
    run_real_corpus_test()