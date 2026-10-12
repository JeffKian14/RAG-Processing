import os
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_step4_test():
    mock_html_path = "mock_test_step4.html"
    mock_html_content = """
    <h1>Visual Assets Guide</h1>
    
    <p>1. Standalone image with alt tag:</p>
    <img src="diagram.png" alt="System architecture">
    
    <ul>
        <li>First point after the image</li>
        <li>Second point before the figure</li>
    </ul>
    
    <p>2. Figure with formatting in the caption:</p>
    <figure>
        <img src="chart.png" alt="Sales chart">
        <figcaption>Monthly sales <strong>performance</strong></figcaption>
    </figure>
    
    <p>3. Image missing both alt text and caption:</p>
    <img src="spacer.png">
    
    <figure>
        <figcaption>Caption without image</figcaption>
    </figure>
    
    <table>
        <tr><th>Table follows the image</th></tr>
        <tr><td>Data row</td></tr>
    </table>
    """
    
    with open(mock_html_path, 'w', encoding='utf-8') as f:
        f.write(mock_html_content)
        
    meta = DocumentMetadata(enterprise="Aventro Motors", source_filename="mock.html", source_format="html")
    doc = parse_html_to_normalized(mock_html_path, "doc_mock_4", meta)
    
    print(f"TITLE: {doc.title}\n" + "="*40)
    for i, section in enumerate(doc.sections):
        if not section.blocks:
            continue
        print(f"\nSECTION: {' > '.join(section.hierarchy)}")
        for block in section.blocks:
            if block.block_type == "text":
                print(f"  [TEXT] {block.text}")
            elif block.block_type == "list":
                print(f"  [LIST] {len(block.items)} items")
            elif block.block_type == "table":
                print(f"  [TABLE] {len(block.rows)} row(s)")
            elif block.block_type == "image":
                print(f"  [IMAGE] alt: {repr(block.alt_text)} | caption: {repr(block.caption)}")
                
    os.remove(mock_html_path)

if __name__ == "__main__":
    run_step4_test()