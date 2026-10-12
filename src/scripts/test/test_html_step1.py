import os
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_step1_test():
    # 1. Create a mock HTML file with edge cases
    mock_html_path = "mock_test_step1.html"
    mock_html_content = """
    <h1>Company Overview</h1>
    <p>Welcome to <strong>Aventro Motors</strong>. <span>We build cars.</span></p>
    
    <h2>## Regional Offices</h2>
    <p>Our main office is located in Mumbai.<br>Secondary office in Delhi.</p>
    
    <h3>Mumbai Details</h3>
    <p>Contact us at:<br><br>Email: info@aventromotors.com<br>Phone: 123-456</p>
    """
    
    with open(mock_html_path, 'w', encoding='utf-8') as f:
        f.write(mock_html_content)
        
    meta = DocumentMetadata(enterprise="Aventro Motors", source_filename="mock.html", source_format="html")
    
    # 2. Parse the file
    doc = parse_html_to_normalized(mock_html_path, "doc_mock_1", meta)
    
    # 3. Print the output structure
    print(f"TITLE: {doc.title}\n" + "="*40)
    for i, section in enumerate(doc.sections):
        print(f"\nSECTION {i+1}: {' > '.join(section.hierarchy)}")
        for block in section.blocks:
            # Replace newlines with a visible marker for terminal inspection
            preview_text = block.text.replace('\n', ' [NEWLINE] ')
            print(f"  [{block.block_type.upper()}] {preview_text}")

    # Clean up
    os.remove(mock_html_path)

if __name__ == "__main__":
    run_step1_test()