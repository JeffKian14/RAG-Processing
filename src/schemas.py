from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union, Annotated

class DocumentMetadata(BaseModel):
    enterprise: str
    source_filename: str
    source_format: str = Field(description="e.g., 'pdf', 'docx', 'md', 'html', 'pptx'")
    document_version: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    access_groups: List[str] = Field(default_factory=list)

class TextBlock(BaseModel):
    block_type: Literal["text"] = "text"
    text: str
    page_number: Optional[int] = None
    slide_number: Optional[int] = None

class TableBlock(BaseModel):
    block_type: Literal["table"] = "table"
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    page_number: Optional[int] = None
    slide_number: Optional[int] = None

class ListItem(BaseModel):
    """A single item in a list, representing semantic text and any nested lists."""
    text: str = Field(description="The pure semantic text of the list item.")
    sub_lists: List['ListBlock'] = Field(
        default_factory=list,
        description="Nested ordered or unordered lists contained within this item."
    )

class ListBlock(BaseModel):
    block_type: Literal["list"] = "list"
    list_type: Literal["ordered", "unordered"]
    items: List[ListItem] = Field(default_factory=list)
    page_number: Optional[int] = None
    slide_number: Optional[int] = None

class ImageBlock(BaseModel):
    block_type: Literal["image"] = "image"
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    page_number: Optional[int] = None
    slide_number: Optional[int] = None

# Resolve forward references for recursive typing
ListItem.model_rebuild()

# The updated ContentBlock contract representing purely semantic structures
ContentBlock = Annotated[
    Union[TextBlock, TableBlock, ListBlock, ImageBlock], 
    Field(discriminator="block_type")
]

class Section(BaseModel):
    hierarchy: List[str] = Field(default_factory=list)
    blocks: List[ContentBlock] = Field(default_factory=list)

class NormalizedDocument(BaseModel):
    document_id: str
    title: str
    metadata: DocumentMetadata
    sections: List[Section]

class ChunkUnit(BaseModel):
    text: str
    block_type: Literal["text", "list", "table", "image"]
    section_hierarchy: List[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    slide_number: Optional[int] = None


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    chunk_method: str
    text: str
    enterprise: str
    source_filename: str
    source_format: str
    section_hierarchy: List[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    parent_chunk_id: Optional[str] = None
    child_chunk_ids: List[str] = Field(default_factory=list)
    token_count: Optional[int] = None