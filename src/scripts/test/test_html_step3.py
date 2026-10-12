import os
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_step3_test():
    mock_html_path = "mock_test_step3.html"
    mock_html_content = """
    <h1>Table Tests</h1>
    
    <h2>1. Thead + Tbody</h2>
    <table>
        <thead>
            <tr><th>Name</th><th>Role</th></tr>
        </thead>
        <tbody>
            <tr><td>Alice</td><td>Engineer</td></tr>
        </tbody>
    </table>
    
    <h2>2. No Thead, Implicit TH (plus formatting)</h2>
    <table>
        <tr>
            <th>Item</th>
            <th>Status</th>
        </tr>
        <tr>
            <td>Server</td>
            <td><strong>Active</strong><br>Online</td>
        </tr>
    </table>
    
    <h2>3. No Headers At All</h2>
    <table>
        <tr>
            <td>Data 1</td>
            <td>Data 2</td>
        </tr>
        <tr>
            <td>Data 3</td>
            <td>Data 4</td>
        </tr>
    </table>
    
    <h2>4. Mixed TR and TBODY (Order Test)</h2>
    <table>
        <tr><td>Row 1 (Direct TR)</td></tr>
        <tbody>
            <tr><td>Row 2 (Inside Tbody)</td></tr>
        </tbody>
        <tr><td>Row 3 (Direct TR)</td></tr>
    </table>
    """
    
    with open(mock_html_path, 'w', encoding='utf-8') as f:
        f.write(mock_html_content)
        
    meta = DocumentMetadata(enterprise="CloudWay-24", source_filename="mock.html", source_format="html")
    doc = parse_html_to_normalized(mock_html_path, "doc_mock_3", meta)
    
    print(f"TITLE: {doc.title}\n" + "="*40)
    for i, section in enumerate(doc.sections):
        if not section.blocks:
            continue
        print(f"\nSECTION: {' > '.join(section.hierarchy)}")
        for block in section.blocks:
            if block.block_type == "table":
                print(f"  [TABLE]")
                print(f"    ├─ Headers: {block.headers}")
                print(f"    └─ Rows   : {len(block.rows)}")
                for r_idx, row in enumerate(block.rows):
                    row_preview = [c.replace('\n', ' [NEWLINE] ') for c in row]
                    print(f"       Row {r_idx+1}: {row_preview}")
                
    os.remove(mock_html_path)

if __name__ == "__main__":
    run_step3_test()