import os
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_step5_test():
    mock_html_path = "mock_test_step5.html"
    mock_html_content = """
    <h1>Table Conversions</h1>
    
    <h2>Case 1: Pseudo-table</h2>
    <table>
        <tbody>
            <tr><td>## Mumbai – Maharashtra</td></tr>
            <tr><td>1. Indian Oil, Bandra Kurla Complex</td></tr>
            <tr><td>2. HPCL, Cuffe Parade</td></tr>
            <tr><td>3. BPCL, Andheri West</td></tr>
        </tbody>
    </table>
    
    <h2>Case 2: Normal 1-col with Thead</h2>
    <table>
        <thead>
            <tr><th>Employee</th></tr>
        </thead>
        <tbody>
            <tr><td>Alice</td></tr>
            <tr><td>Bob</td></tr>
        </tbody>
    </table>
    
    <h2>Case 3: Normal 1-col without Headers</h2>
    <table>
        <tbody>
            <tr><td>Alice</td></tr>
            <tr><td>Bob</td></tr>
            <tr><td>Charlie</td></tr>
        </tbody>
    </table>
    """
    
    with open(mock_html_path, 'w', encoding='utf-8') as f:
        f.write(mock_html_content)
        
    meta = DocumentMetadata(enterprise="Aventro Motors", source_filename="mock.html", source_format="html")
    doc = parse_html_to_normalized(mock_html_path, "doc_mock_5", meta)
    
    print(f"TITLE: {doc.title}\n" + "="*40)
    for i, section in enumerate(doc.sections):
        if not section.blocks:
            continue
        print(f"\nSECTION: {' > '.join(section.hierarchy)}")
        for block in section.blocks:
            if block.block_type == "text":
                print(f"  [TEXT] {block.text}")
            elif block.block_type == "list":
                print(f"  [LIST] {block.list_type}")
                for item in block.items:
                    print(f"    - {item.text}")
            elif block.block_type == "table":
                print(f"  [TABLE]")
                print(f"    ├─ Headers: {block.headers}")
                print(f"    └─ Rows   : {len(block.rows)}")
                for r_idx, row in enumerate(block.rows):
                    print(f"       {row}")
                
    os.remove(mock_html_path)

if __name__ == "__main__":
    run_step5_test()