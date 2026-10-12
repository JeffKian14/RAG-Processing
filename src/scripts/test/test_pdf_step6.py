import os
import pymupdf
from src.parsers.pdf_parser import parse_pdf_to_lines

def create_mock_pdf(path: str):
    doc = pymupdf.open()
    page = doc.new_page()
    
    # 1. Normal paragraph line
    page.insert_text((50, 50), "This is a normal paragraph line.", fontsize=10)
    
    # 2. Fragmented spans with edge whitespace preserved
    page.insert_text((50, 100), " Frag", fontsize=10)
    page.insert_text((75, 100), "mented ", fontsize=10)
    
    # 3. Multi-column separation demonstrating horizontal separation
    page.insert_text((50, 150), "Electric", fontsize=10)
    page.insert_text((250, 150), "ZX", fontsize=10)
    
    # 4. Font metadata
    page.insert_font(fontname="hebo", fontbuffer=pymupdf.Font("helv", is_bold=True).buffer)
    page.insert_text((50, 200), "Bold Heading", fontname="hebo", fontsize=14)
    
    doc.save(path)
    doc.close()

def run_step6e_test():
    mock_pdf_path = "mock_test_step6e.pdf"
    create_mock_pdf(mock_pdf_path)
    
    lines = parse_pdf_to_lines(mock_pdf_path)
    
    print("=" * 70)
    print("PDF PARSER TEST: RAW SPANS & SPATIAL VALIDATION")
    print("=" * 70)
    
    for line in lines:
        print(f"\n[Block {line.block_idx} | Line {line.line_idx}] BBox: {[round(c,1) for c in line.bbox]}")
        print(f"Total Spans: {len(line.spans)}")
        for i, span in enumerate(line.spans):
            gap = "N/A" if i == 0 else round(span.x0 - line.spans[i-1].x1, 1)
            print(f"  Span {i}: {span.text!r:<20} | x0: {span.x0:5.1f} | gap: {gap:>5} | BBox: {[round(c,1) for c in (span.x0, span.y0, span.x1, span.y1)]}")

    os.remove(mock_pdf_path)

if __name__ == "__main__":
    run_step6e_test()