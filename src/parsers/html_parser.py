import re
import bs4
from bs4 import BeautifulSoup
from typing import List, Set, Optional, Union
from src.schemas import DocumentMetadata, NormalizedDocument, Section, TextBlock, ContentBlock, ListBlock, ListItem, TableBlock, ImageBlock

def safe_extract_text_excluding(element: bs4.Tag, exclude_nodes: Set[bs4.Tag]) -> str:
    texts = []
    
    # basic cleanout of whitespace and line breaks
    def walk(node):
        if node in exclude_nodes:
            return
        if isinstance(node, bs4.NavigableString):
            cleaned_string = re.sub(r'\s+', ' ', str(node))
            texts.append(cleaned_string)
        elif getattr(node, 'name', None) == 'br':
            texts.append('\n')
        elif hasattr(node, 'children'):
            for child in node.children:
                walk(child)
                
    # keep only the text from the element, excluding specified nodes
    walk(element)
    raw_text = "".join(texts)
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in raw_text.split('\n')]
    return "\n".join(filter(None, lines))

# extract semantic text from an element
def extract_semantic_text(element: bs4.Tag) -> str:
    if not element:
        return ""
    return safe_extract_text_excluding(element, exclude_nodes=set())

# make sure to handle nested lists instead of just generate a flat list of items
def process_list(list_node: bs4.Tag) -> ListBlock:
    list_type = "ordered" if list_node.name == 'ol' else "unordered"
    items = []
    
    for li in list_node.find_all('li', recursive=False):
        nested_lists = []
        for child_list in li.find_all(['ul', 'ol']):
            if child_list.find_parent('li') == li:
                nested_lists.append(child_list)
        
        item_text = safe_extract_text_excluding(li, exclude_nodes=set(nested_lists))
        sub_blocks = [process_list(nested) for nested in nested_lists]
        
        items.append(ListItem(text=item_text, sub_lists=sub_blocks))
        
    return ListBlock(list_type=list_type, items=items)

# process a table node, with special handling for pseudo-tables
def process_table(table_node: bs4.Tag) -> Union[TableBlock, List[ContentBlock]]:
    # 1. Structural Pre-check for Pseudo-table Heuristic
    has_thead = table_node.find('thead') is not None
    has_th = table_node.find('th') is not None
    
    # check if there is a list-like structure in the table (e.g., a single column with numbered items)
    row_nodes = []
    for child in table_node.find_all(['tbody', 'tr'], recursive=False):
        if child.name == 'tbody':
            row_nodes.extend(child.find_all('tr', recursive=False))
        else:
            row_nodes.append(child)

    # check for pseudo-table: single column with numbered items and a heading
    #  ##sdsada
    #  1. First item
    #  2. Second item
    if not has_thead and not has_th and len(row_nodes) > 1:
        # Check exactly 1 column across all rows
        is_one_col = all(len(r.find_all(['td', 'th'], recursive=False)) == 1 for r in row_nodes)
        
        if is_one_col:
            cell_texts = [extract_semantic_text(r.find('td', recursive=False)) for r in row_nodes]
            first_text = cell_texts[0].strip()
            
            # Check semantic triggers
            if first_text.startswith("##"):
                is_all_numbered = all(re.match(r'^\s*\d+\.\s+', text) for text in cell_texts[1:])
                
                if is_all_numbered:
                    # CONVERSION: Pseudo-table matched
                    heading_text = re.sub(r'^\s*##\s*', '', first_text).strip()
                    text_block = TextBlock(text=heading_text)
                    
                    list_items = []
                    for text in cell_texts[1:]:
                        # Strip the manual number prefix (e.g., "1. ")
                        clean_text = re.sub(r'^\s*\d+\.\s+', '', text).strip()
                        list_items.append(ListItem(text=clean_text))
                        
                    list_block = ListBlock(list_type="ordered", items=list_items)
                    return [text_block, list_block]
            
    # 2. Normal Table Processing
    headers = []
    final_row_nodes = []
    
    for child in table_node.find_all(recursive=False):
        if child.name == 'thead':
            if not headers:
                header_row = child.find('tr', recursive=False)
                if header_row:
                    headers = [extract_semantic_text(cell) for cell in header_row.find_all(['th', 'td'], recursive=False)]
        elif child.name == 'tbody':
            final_row_nodes.extend(child.find_all('tr', recursive=False))
        elif child.name == 'tr':
            final_row_nodes.append(child)

    rows = []
    for i, tr in enumerate(final_row_nodes):
        cells = [extract_semantic_text(cell) for cell in tr.find_all(['td', 'th'], recursive=False)]
        
        if not headers and i == 0 and tr.find('th', recursive=False):
            headers = cells
            continue 
            
        if cells:
            rows.append(cells)
            
    return TableBlock(headers=headers, rows=rows)

# process an image or figure node, extracting alt text and caption only if available
def process_image_or_figure(element: bs4.Tag) -> Optional[ImageBlock]:
    alt_text = None
    caption = None
    
    if element.name == 'figure':
        img_node = element.find('img')
        if not img_node:
            return None
            
        alt_text = img_node.get('alt')
        caption_node = element.find('figcaption')
        if caption_node:
            caption = extract_semantic_text(caption_node)
            
    elif element.name == 'img':
        alt_text = element.get('alt')
        
    return ImageBlock(alt_text=alt_text, caption=caption)

# parse an HTML file into a normalized document structure
# it will store extracted sections, headings, paragraphs, lists, tables, and images in a structured format
# each heading's content is grouped under its respective section, preserving the document's hierarchy
def parse_html_to_normalized(file_path: str, document_id: str, metadata: DocumentMetadata) -> NormalizedDocument:
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    sections: List[Section] = []
    current_hierarchy: List[str] = []
    current_blocks: List[ContentBlock] = []

    def push_section():
        if current_blocks:
            sections.append(Section(
                hierarchy=list(current_hierarchy),
                blocks=list(current_blocks)
            ))
            current_blocks.clear()

    title = "Untitled Document"
    
    target_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'table', 'img', 'figure']
    all_targets = soup.find_all(target_tags)
    
    root_elements = [
        el for el in all_targets 
        if not any(parent.name in target_tags for parent in el.parents)
    ]

    for element in root_elements:
        tag_name = element.name
        
        if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            push_section()
            level = int(tag_name[1])
            heading_text = extract_semantic_text(element)
            heading_text = re.sub(r'^#+\s*', '', heading_text)
            
            if not current_hierarchy and level == 1 and title == "Untitled Document":
                title = heading_text
                
            if level <= len(current_hierarchy):
                current_hierarchy = current_hierarchy[:level-1]
            current_hierarchy.append(heading_text)
            
        elif tag_name == 'p':
            text = extract_semantic_text(element)
            if text:
                current_blocks.append(TextBlock(text=text))
                
        elif tag_name in ['ul', 'ol']:
            current_blocks.append(process_list(element))
            
        elif tag_name == 'table':
            # Handle multiple returns from pseudo-tables
            table_result = process_table(element)
            if isinstance(table_result, list):
                current_blocks.extend(table_result)
            else:
                current_blocks.append(table_result)
            
        elif tag_name in ['img', 'figure']:
            image_block = process_image_or_figure(element)
            if image_block is not None:
                current_blocks.append(image_block)

    push_section()

    if title == "Untitled Document":
        title = metadata.source_filename

    return NormalizedDocument(document_id=document_id, title=title, metadata=metadata, sections=sections)