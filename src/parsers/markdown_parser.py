# import re
# from typing import List
# from src.schemas import DocumentMetadata, NormalizedDocument, Section, TextBlock, TableBlock, ContentBlock


# def parse_markdown_to_normalized(file_path: str, document_id: str, metadata: DocumentMetadata) -> NormalizedDocument:
#     """
#     Reads a Markdown file and converts it into the NormalizedDocument schema,
#     preserving text/table ordering and heading hierarchy.
#     """
#     with open(file_path, 'r', encoding='utf-8') as f:
#         lines = f.readlines()

#     sections: List[Section] = []
#     current_hierarchy: List[str] = []
#     current_blocks: List[ContentBlock] = []
    
#     text_buffer = []
#     table_buffer = []
#     in_table = False

#     def flush_text():
#         if text_buffer:
#             content = "\n".join(text_buffer).strip()
#             if content:
#                 current_blocks.append(TextBlock(text=content))
#             text_buffer.clear()

#     def flush_table():
#         if table_buffer:
#             headers = []
#             rows = []
#             for i, row_str in enumerate(table_buffer):
#                 # Clean bounding pipes and split
#                 clean_row = row_str.strip().strip('|')
#                 cells = [cell.strip() for cell in clean_row.split('|')]
                
#                 if i == 0:
#                     headers = cells
#                 elif i == 1 and all(set(c).issubset({'-', ':', ' '}) for c in cells if c):
#                     # Skip Markdown separator row (e.g., |---|---|)
#                     continue
#                 else:
#                     rows.append(cells)
            
#             if headers or rows:
#                 current_blocks.append(TableBlock(headers=headers, rows=rows))
#             table_buffer.clear()

#     def push_section():
#         flush_text()
#         flush_table()
#         if current_blocks:
#             sections.append(Section(
#                 hierarchy=list(current_hierarchy),
#                 blocks=list(current_blocks)
#             ))
#             current_blocks.clear()

#     title = "Untitled Document"

#     for line in lines:
#         stripped_line = line.strip()
        
#         # Flush blocks on empty lines to keep paragraphs discrete
#         if not stripped_line:
#             if in_table:
#                 flush_table()
#                 in_table = False
#             flush_text()
#             continue

#         # Header detection
#         header_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
#         if header_match:
#             push_section()  # Save current section before starting a new one
            
#             level = len(header_match.group(1))
#             heading_text = header_match.group(2).strip()
            
#             if not current_hierarchy and level == 1:
#                 title = heading_text
                
#             # Maintain hierarchical array structure
#             if level <= len(current_hierarchy):
#                 current_hierarchy = current_hierarchy[:level-1]
#             current_hierarchy.append(heading_text)
#             continue

#         # Table row detection (strict check for bounding pipes)
#         if stripped_line.startswith('|') and stripped_line.endswith('|'):
#             if not in_table:
#                 flush_text()  # Ordering preservation: save text before the table starts
#                 in_table = True
#             table_buffer.append(stripped_line)
#             continue

#         # Exiting a table block
#         if in_table:
#             flush_table()
#             in_table = False

#         # Accumulate standard text
#         text_buffer.append(stripped_line)

#     # Clean up EOF
#     push_section()
    
#     if title == "Untitled Document":
#         title = metadata.source_filename

#     return NormalizedDocument(
#         document_id=document_id,
#         title=title,
#         metadata=metadata,
#         sections=sections
#     )

# # --- Example Usage ---
# if __name__ == "__main__":
#     # Simulated metadata mapping from dataset filepath structure
#     meta = DocumentMetadata(
#         enterprise="Aventro Motors",
#         source_filename="hr_policy.md",
#         source_format="md"
#     )
    
#     # You would point this to a real file path like:
#     # "Dataset/RAG-Multi-Corpus-main/datasets/Aventro Motors/md/hr_policy.md"
#     # doc = parse_markdown_to_normalized("path/to/file.md", "doc_123", meta)

# import re
# from typing import List
# from src.schemas import DocumentMetadata, NormalizedDocument, Section, TextBlock, TableBlock, ContentBlock

# def parse_markdown_to_normalized(file_path: str, document_id: str, metadata: DocumentMetadata) -> NormalizedDocument:
#     with open(file_path, 'r', encoding='utf-8') as f:
#         lines = f.readlines()

#     sections: List[Section] = []
#     current_hierarchy: List[str] = []
#     current_blocks: List[ContentBlock] = []
    
#     text_buffer = []
#     table_buffer = []
#     in_table = False

#     def flush_text():
#         if text_buffer:
#             content = "\n".join(text_buffer).strip()
#             if content:
#                 current_blocks.append(TextBlock(text=content))
#             text_buffer.clear()

#     def flush_table():
#         if table_buffer:
#             headers = []
#             rows = []
#             for i, row_str in enumerate(table_buffer):
#                 clean_row = row_str.strip().strip('|')
#                 cells = [cell.strip() for cell in clean_row.split('|')]
                
#                 if i == 0:
#                     headers = cells
#                 elif i == 1 and all(set(c).issubset({'-', ':', ' '}) for c in cells if c):
#                     continue
#                 else:
#                     rows.append(cells)
            
#             if headers or rows:
#                 current_blocks.append(TableBlock(headers=headers, rows=rows))
#             table_buffer.clear()

#     def push_section():
#         flush_text()
#         flush_table()
#         if current_blocks:
#             sections.append(Section(
#                 hierarchy=list(current_hierarchy),
#                 blocks=list(current_blocks)
#             ))
#             current_blocks.clear()

#     title = "Untitled Document"

#     for line in lines:
#         stripped_line = line.strip()
        
#         if not stripped_line:
#             if in_table:
#                 flush_table()
#                 in_table = False
#             flush_text()
#             continue

#         header_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
#         if header_match:
#             push_section()
            
#             level = len(header_match.group(1))
#             heading_text = header_match.group(2).strip()
            
#             if not current_hierarchy and level == 1:
#                 title = heading_text
                
#             if level <= len(current_hierarchy):
#                 current_hierarchy = current_hierarchy[:level-1]
#             current_hierarchy.append(heading_text)
#             continue

#         if '|' in stripped_line and not stripped_line.startswith('#'):
#             if not in_table:
#                 flush_text()
#                 in_table = True
#             table_buffer.append(stripped_line)
#             continue

#         if in_table:
#             flush_table()
#             in_table = False

#         # --- FIX: Ignore Markdown horizontal rules ---
#         if re.match(r'^[-*_]{3,}\s*$', stripped_line):
#             continue

#         text_buffer.append(stripped_line)

#     push_section()
    
#     if title == "Untitled Document":
#         title = metadata.source_filename

#     return NormalizedDocument(
#         document_id=document_id,
#         title=title,
#         metadata=metadata,
#         sections=sections
#     )

import re
from typing import List
from src.schemas import DocumentMetadata, NormalizedDocument, Section, TextBlock, TableBlock, ContentBlock

def parse_markdown_to_normalized(file_path: str, document_id: str, metadata: DocumentMetadata) -> NormalizedDocument:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sections: List[Section] = []
    current_hierarchy: List[str] = []
    current_blocks: List[ContentBlock] = []
    
    text_buffer = []
    table_buffer = []

    def flush_text():
        if text_buffer:
            content = "\n".join(text_buffer).strip()
            if content:
                current_blocks.append(TextBlock(text=content))
            text_buffer.clear()

    def flush_table():
        if not table_buffer:
            return
            
        # Validate table by checking for a structural separator row
        is_valid_table = False
        if len(table_buffer) >= 2:
            sep = table_buffer[1].strip()
            # Must contain '|' and '-', and only valid separator characters
            if '|' in sep and '-' in sep and bool(re.match(r'^[\s:\|-]+$', sep)):
                is_valid_table = True
                
        if is_valid_table:
            # Commit pending text before committing the table
            flush_text()
            
            headers = []
            rows = []
            for i, row_str in enumerate(table_buffer):
                clean_row = row_str.strip().strip('|')
                cells = [cell.strip() for cell in clean_row.split('|')]
                
                if i == 0:
                    headers = cells
                elif i == 1:
                    continue # Skip the separator row
                else:
                    rows.append(cells)
            
            if headers or rows:
                current_blocks.append(TableBlock(headers=headers, rows=rows))
        else:
            # False positive: downgrade the buffer to standard text
            text_buffer.extend(table_buffer)
            
        table_buffer.clear()

    def push_section():
        flush_table()
        flush_text()
        if current_blocks:
            sections.append(Section(
                hierarchy=list(current_hierarchy),
                blocks=list(current_blocks)
            ))
            current_blocks.clear()

    title = "Untitled Document"

    for line in lines:
        stripped_line = line.strip()
        
        if not stripped_line:
            flush_table()
            flush_text()
            continue

        header_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
        if header_match:
            push_section()
            
            level = len(header_match.group(1))
            heading_text = header_match.group(2).strip()
            
            if not current_hierarchy and level == 1:
                title = heading_text
                
            if level <= len(current_hierarchy):
                current_hierarchy = current_hierarchy[:level-1]
            current_hierarchy.append(heading_text)
            continue

        # Buffer potential table lines
        if '|' in stripped_line and not stripped_line.startswith('#'):
            table_buffer.append(stripped_line)
            continue
            
        # If the line lacks a pipe, any active table buffer is finalized
        if table_buffer:
            flush_table()

        # Safely ignore horizontal rules (only hits if it wasn't captured as a table separator above)
        if re.match(r'^[-*_]{3,}\s*$', stripped_line):
            continue

        text_buffer.append(stripped_line)

    push_section()
    
    if title == "Untitled Document":
        title = metadata.source_filename

    return NormalizedDocument(
        document_id=document_id,
        title=title,
        metadata=metadata,
        sections=sections
    )