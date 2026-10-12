from src.schemas import ContentBlock, TextBlock, ListBlock, TableBlock, ImageBlock


def render_list(block: ListBlock, level: int = 0) -> str:
    lines = []
    for i, item in enumerate(block.items, 1):
        prefix = f"{i}. " if block.list_type == "ordered" else "- "
        lines.append(f"{'  ' * level}{prefix}{item.text}")
        for sub_list in item.sub_lists: lines.append(render_list(sub_list, level + 1))
    return "\n".join(lines)


def render_table(block: TableBlock) -> str:
    lines = [" | ".join(block.headers)] if block.headers else []
    lines.extend(" | ".join(row) for row in block.rows)
    return "\n".join(lines)


def render_block(block: ContentBlock) -> str:
    if isinstance(block, TextBlock): return block.text
    if isinstance(block, ListBlock): return render_list(block)
    if isinstance(block, TableBlock): return render_table(block)
    if isinstance(block, ImageBlock): return " - ".join(x for x in (block.alt_text, block.caption) if x)
    return ""