import os
from src.schemas import DocumentMetadata
from src.parsers.html_parser import parse_html_to_normalized

def run_step2_test():
    mock_html_path = "mock_test_step2.html"
    mock_html_content = """
    <h1>Operating Procedures</h1>
    <p>Follow these standard procedures carefully:</p>
    <ol>
        <li>
            Step 1
            <p>Initialize the system</p>
        </li>
        <li>
            Step 2: Diagnostics<br>Warning: Do not skip.
            <ul>
                <li>Check A: Power levels</li>
                <li>
                    Check B: Network connection
                    <ol>
                        <li>Ping local server</li>
                        <li>Verify external DNS</li>
                    </ol>
                </li>
            </ul>
        </li>
        <li>Step 3: Proceed with operation</li>
    </ol>
    """
    
    with open(mock_html_path, 'w', encoding='utf-8') as f:
        f.write(mock_html_content)
        
    meta = DocumentMetadata(enterprise="CloudWay-24", source_filename="mock.html", source_format="html")
    doc = parse_html_to_normalized(mock_html_path, "doc_mock_2", meta)
    
    print(f"TITLE: {doc.title}\n" + "="*40)
    for section in doc.sections:
        for block in section.blocks:
            if block.block_type == "text":
                print(f"[TEXT] {block.text}")
            elif block.block_type == "list":
                print(f"[LIST] ({block.list_type})")
                def print_items(items, indent="  "):
                    for item in items:
                        text_preview = item.text.replace('\n', ' [NEWLINE] ')
                        print(f"{indent}- {text_preview}")
                        for sub in item.sub_lists:
                            print(f"{indent}  [SUBLIST] ({sub.list_type})")
                            print_items(sub.items, indent + "    ")
                print_items(block.items)
                
    os.remove(mock_html_path)

if __name__ == "__main__":
    run_step2_test()