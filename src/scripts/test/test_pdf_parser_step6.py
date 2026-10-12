from src.parsers.pdf_parser import PDFSpan, PDFLine

def create_span(text, x0, x1, size=10.0, is_bold=False):
    return PDFSpan(
        text=text, page_number=1, block_idx=0, line_idx=0,
        x0=x0, y0=100.0, x1=x1, y1=110.0,
        font="Helvetica", size=size, is_bold=is_bold, is_italic=False
    )

def run_tests():
    # 1. Same-word fragmentation
    line1 = PDFLine([create_span("Frag", 50.0, 75.0), create_span("mented", 75.1, 100.0)], 1, 0, 0)
    assert line1.text == "Fragmented", f"Expected 'Fragmented', got {line1.text!r}"
    
    # 2. Normal gap, no whitespace
    line2 = PDFLine([create_span("Hello", 50.0, 75.0), create_span("world", 78.0, 100.0)], 1, 0, 1)
    assert line2.text == "Hello world", f"Expected 'Hello world', got {line2.text!r}"
    
    # 3. Normal gap, trailing whitespace
    line3 = PDFLine([create_span("Hello ", 50.0, 78.0), create_span("world", 81.0, 100.0)], 1, 0, 2)
    assert line3.text == "Hello world", f"Expected 'Hello world', got {line3.text!r}"
    
    # 4. Normal gap, leading whitespace
    line4 = PDFLine([create_span("Hello", 50.0, 75.0), create_span(" world", 78.0, 100.0)], 1, 0, 3)
    assert line4.text == "Hello world", f"Expected 'Hello world', got {line4.text!r}"
    
    # 5. Normal gap, BOTH whitespaces
    line5 = PDFLine([create_span("Hello ", 50.0, 78.0), create_span(" world", 81.0, 100.0)], 1, 0, 4)
    assert line5.text == "Hello world", f"Expected 'Hello world', got {line5.text!r}"

    # 6. Different formatting (Doesn't force artificial spaces)
    line6 = PDFLine([create_span("Super", 50.0, 75.0, is_bold=True), create_span("man", 75.1, 90.0)], 1, 0, 5)
    assert line6.text == "Superman", f"Expected 'Superman', got {line6.text!r}"

    # 7. Large gap check (Column separation)
    line7 = PDFLine([create_span("Electric", 50.0, 90.0), create_span("ZX", 250.0, 270.0)], 1, 0, 6)
    assert line7.text == "Electric\tZX", f"Expected 'Electric\\tZX', got {line7.text!r}"

    # 8. Multiple spans forming a sentence
    line8 = PDFLine([
        create_span("This", 50.0, 65.0),
        create_span("is", 68.0, 75.0),
        create_span("a", 78.0, 83.0),
        create_span("test.", 86.0, 100.0)
    ], 1, 0, 7)
    assert line8.text == "This is a test.", f"Expected 'This is a test.', got {line8.text!r}"

    print("All 6E-4 assertions passed. Whitespace logic is mathematically exact.")

if __name__ == '__main__':
    run_tests()