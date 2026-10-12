import pymupdf
import re
from dataclasses import dataclass
from typing import List, Tuple

@dataclass(frozen=True)
# initializing the PDFSpan class to represent a single continuous text span with uniform formatting
class PDFSpan:
    """Represents a single continuous text span with uniform formatting (Immutable)."""
    text: str
    page_number: int
    block_idx: int
    line_idx: int
    x0: float
    y0: float
    x1: float
    y1: float
    font: str
    size: float
    is_bold: bool
    is_italic: bool


@dataclass
class PDFLine:

    # initializing all the attributes of the PDFLine class
    spans: List[PDFSpan]
    page_number: int
    block_idx: int
    line_idx: int
    page_width: float = 0.0
    page_height: float = 0.0

    # defining a property to calculate the bounding box of a line (with content) based on its spans in the PDF
    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Calculates the bounding box for the entire reconstructed line."""
        if not self.spans:
            return 0.0, 0.0, 0.0, 0.0
        x0 = min(s.x0 for s in self.spans)
        y0 = min(s.y0 for s in self.spans)
        x1 = max(s.x1 for s in self.spans)
        y1 = max(s.y1 for s in self.spans)
        return x0, y0, x1, y1

    @property
    # first make sure to sort the spans by their x0 coordinate to ensure they are in left-to-right order
    # then reconstruct the text of the line by concatenating the text of each span, inserting spaces or tabs based on the gaps between spans
    # return the reconstructed text for each line, preserving the original formatting as much as possible
    def text(self) -> str:
        if not self.spans:
            return ""
        
        result = self.spans[0].text
        
        for i in range(1, len(self.spans)):
            prev_span = self.spans[i-1]
            curr_span = self.spans[i]
            
            gap = curr_span.x0 - prev_span.x1
            font_size = prev_span.size if prev_span.size > 0 else 10.0
            
            space_thresh = font_size * 0.2
            large_gap_thresh = font_size * 1.5
            
            prev_has_space = result.endswith(" ")
            curr_has_space = curr_span.text.startswith(" ")
            
            if gap > large_gap_thresh:
                if prev_has_space:
                    result = result[:-1]
                result += "\t" + (curr_span.text[1:] if curr_has_space else curr_span.text)
                
            elif gap > space_thresh:
                if prev_has_space and curr_has_space:
                    result += curr_span.text[1:]
                elif prev_has_space or curr_has_space:
                    result += curr_span.text
                else:
                    result += " " + curr_span.text
                    
            else:
                if prev_has_space and curr_has_space:
                    result += curr_span.text[1:]
                else:
                    result += curr_span.text
                    
        return result


@dataclass
# initializing the ReconstructedTextUnit class to represent a reconstructed text unit that may consist of one or more PDFLine objects
class ReconstructedTextUnit:
    text: str
    source_lines: List[PDFLine]

@dataclass
# initializing the FilteredUnit class to represent a filtered text unit along with the reason for filtering
class FilteredUnit:
    unit: ReconstructedTextUnit
    reason: str  # 'page_number', 'repeated_header', 'repeated_footer'

@dataclass
# initializing the FilterResult class to represent the result of filtering, containing kept and filtered text units
class FilterResult:
    kept_units: List[ReconstructedTextUnit]
    filtered_units: List[FilteredUnit]


def parse_pdf_to_lines(file_path: str) -> List[PDFLine]:
    # convert a PDF file into a list of PDFLine objects, each representing a line of text with its associated spans and metadata
    doc = pymupdf.open(file_path)
    all_lines = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        p_width = float(page.rect.width)
        p_height = float(page.rect.height)
        
        dict_data = page.get_text("dict")

        for b_idx, block in enumerate(dict_data.get("blocks", [])):
            if block.get("type") != 0:
                continue
            
            for l_idx, line in enumerate(block.get("lines", [])):
                raw_spans = []
                
                for span in line.get("spans", []):
                    raw_text = span.get("text", "")
                    
                    if not raw_text.strip():
                        continue
                        
                    x0, y0, x1, y1 = span.get("bbox", [0, 0, 0, 0])
                    font = span.get("font", "Unknown")
                    size = span.get("size", 0.0)
                    flags = span.get("flags", 0)
                    
                    is_bold = "bold" in font.lower() or bool(flags & 2**4)
                    is_italic = "italic" in font.lower() or bool(flags & 2**1)
                    
                    raw_spans.append(PDFSpan(
                        text=raw_text,
                        page_number=page_num,
                        block_idx=b_idx,
                        line_idx=l_idx,
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        font=font,
                        size=size,
                        is_bold=is_bold,
                        is_italic=is_italic
                    ))
                    
                if not raw_spans:
                    continue
                    
                # Sort the spans by their x0 coordinate to ensure they are in left-to-right order
                raw_spans.sort(key=lambda s: s.x0)
                
                validated_groups = []
                current_group = []
                
                # Group spans into lines based on their vertical overlap, ensuring that spans that are close together vertically are treated as part of the same line
                for span in raw_spans:
                    if not current_group:
                        current_group.append(span)
                    else:
                        g_y0 = min(s.y0 for s in current_group)
                        g_y1 = max(s.y1 for s in current_group)
                        
                        if span.y1 <= g_y0 or span.y0 >= g_y1:
                            validated_groups.append(current_group)
                            current_group = [span]
                        else:
                            current_group.append(span)

                # make sure to add the last group if it exists  
                if current_group:
                    validated_groups.append(current_group)
                    
                # create a PDFLine for each validated group of spans, capturing the page number, block index, line index, and page dimensions
                for group in validated_groups:
                    all_lines.append(PDFLine(
                        spans=group,
                        page_number=page_num,
                        block_idx=b_idx,
                        line_idx=l_idx,
                        page_width=p_width,
                        page_height=p_height
                    ))

    doc.close()
    return all_lines

def repair_hyphenation(lines: List[PDFLine]) -> List[ReconstructedTextUnit]:
    # repair hyphenated words that are split across lines in a PDF, merging them into a single reconstructed text unit while preserving the original line information
    if not lines:
        return []

    units = []
    skip_next = False
    
    # Regex to detect obvious list markers
    list_marker_pattern = re.compile(r'^([•\-\*]|\d+\.|\([a-zA-Z0-9]\)|[a-zA-Z]\.)\s')

    for i in range(len(lines)):
        if skip_next:
            skip_next = False
            continue

        curr = lines[i]
        curr_text = curr.text.rstrip()

        # if consists of "" or "–" or "—" at the end, merge with the next line if it starts with a letter and is on the same page, but avoid merging if the next line is a list item or tab-separated
        if i + 1 < len(lines) and curr_text.endswith("-") and not curr_text.endswith("--"):
            next_line = lines[i+1]
            next_text = next_line.text.lstrip()

            is_same_page = curr.page_number == next_line.page_number
            starts_with_letter = next_text[:1].isalpha()
            is_list_marker = bool(list_marker_pattern.match(next_text))
            is_tab_separated = next_text.startswith("\t") or curr_text.endswith("\t-")
            
            if curr.spans:
                last_span = curr.spans[-1]
                font_size = last_span.size if last_span.size > 0 else 10.0
            else:
                font_size = 10.0
                
            y_gap = next_line.bbox[1] - curr.bbox[3]
            is_close = y_gap < (font_size * 3)

            if is_same_page and starts_with_letter and is_close and not is_list_marker and not is_tab_separated:
                base_text = curr_text[:-1]
                merged_text = base_text + next_text
                
                units.append(ReconstructedTextUnit(
                    text=merged_text,
                    source_lines=[curr, next_line]
                ))
                skip_next = True
                continue

        units.append(ReconstructedTextUnit(
            text=curr.text,
            source_lines=[curr]
        ))

    return units

# removes unnecessary content from PDFs, such as page numbers, repeated headers, and repeated footers, while preserving meaningful text for RAG processing.
# Checks text within the top 15% and bottom 15% of each page. Identifies headers and footers repeated across multiple pages (at least 2–3 pages).
# Removes detected repeated headers, footers, and page numbers near page edges. Stores both retained and filtered content, including the reason for filtering.
def filter_edge_noise(units: List[ReconstructedTextUnit]) -> FilterResult:
    """
    Step 6E-6: Detects and filters standalone page numbers and repeated headers/footers.
    """
    if not units:
        return FilterResult([], [])

    unique_pages = {line.page_number for u in units for line in u.source_lines}
    total_pages = len(unique_pages)
    repetition_thresh = 3 if total_pages >= 4 else 2

    header_tracker, footer_tracker = {}, {}

    for u in units:
        if not u.source_lines: continue
        text = u.text.strip()
        if not text: continue
        
        norm_text = re.sub(r'\s+', ' ', text).lower()
        y0 = min(line.bbox[1] for line in u.source_lines)
        y1 = max(line.bbox[3] for line in u.source_lines)
        page_height = u.source_lines[0].page_height if u.source_lines[0].page_height > 0 else 800.0
        page_num = u.source_lines[0].page_number

        if not ((text.isdigit() and len(text) <= 3) or norm_text.startswith("page ")):
            if y0 < page_height * 0.15:
                header_tracker.setdefault(norm_text, set()).add(page_num)
            if y1 > page_height * 0.85:
                footer_tracker.setdefault(norm_text, set()).add(page_num)

    repeated_headers = {txt for txt, pgs in header_tracker.items() if len(pgs) >= repetition_thresh}
    repeated_footers = {txt for txt, pgs in footer_tracker.items() if len(pgs) >= repetition_thresh}

    kept, filtered = [], []

    for u in units:
        if not u.source_lines:
            kept.append(u)
            continue
            
        text = u.text.strip()
        norm_text = re.sub(r'\s+', ' ', text).lower()
        y0 = min(line.bbox[1] for line in u.source_lines)
        y1 = max(line.bbox[3] for line in u.source_lines)
        page_height = u.source_lines[0].page_height if u.source_lines[0].page_height > 0 else 800.0

        is_top_edge = y0 < page_height * 0.15
        is_bottom_edge = y1 > page_height * 0.85
        reason = None

        if (is_top_edge or is_bottom_edge) and ((text.isdigit() and len(text) <= 3) or norm_text.startswith("page ")):
            reason = "page_number"
        elif is_top_edge and norm_text in repeated_headers:
            reason = "repeated_header"
        elif is_bottom_edge and norm_text in repeated_footers:
            reason = "repeated_footer"

        if reason:
            filtered.append(FilteredUnit(u, reason))
        else:
            kept.append(u)

    return FilterResult(kept, filtered)


from collections import defaultdict
import statistics

# ==========================================
# STEP 6E-7: SEMANTIC REGION DETECTION
# ==========================================
@dataclass
class SemanticRegion:
    page_number: int
    units: List[ReconstructedTextUnit]
    x0: float
    y0: float
    x1: float
    y1: float

def detect_semantic_regions(units: List[ReconstructedTextUnit]) -> List[SemanticRegion]:
    if not units:
        return []
    
    regions = []
    pages = defaultdict(list)
    for u in units:
        if u.source_lines:
            pages[u.source_lines[0].page_number].append(u)
    
    for page_num, page_units in pages.items():
        # Sort top-down, then left-right
        page_units.sort(key=lambda u: (min(l.bbox[1] for l in u.source_lines), min(l.bbox[0] for l in u.source_lines)))
        
        active_regions = []
        for unit in page_units:
            ux0 = min(l.bbox[0] for l in unit.source_lines)
            uy0 = min(l.bbox[1] for l in unit.source_lines)
            ux1 = max(l.bbox[2] for l in unit.source_lines)
            uy1 = max(l.bbox[3] for l in unit.source_lines)
            font_size = unit.source_lines[-1].spans[-1].size if (unit.source_lines and unit.source_lines[-1].spans) else 10.0
            
            placed = False
            for reg in active_regions:
                y_gap = uy0 - reg.y1
                
                # Check for vertical proximity AND horizontal compatibility
                if y_gap < (font_size * 2.5):
                    h_overlap = max(0, min(ux1, reg.x1) - max(ux0, reg.x0))
                    x0_aligned = abs(ux0 - reg.x0) < (font_size * 2)
                    
                    if h_overlap > 0 or x0_aligned:
                        reg.units.append(unit)
                        reg.x0, reg.y0 = min(reg.x0, ux0), min(reg.y0, uy0)
                        reg.x1, reg.y1 = max(reg.x1, ux1), max(reg.y1, uy1)
                        placed = True
                        break
                        
            if not placed:
                active_regions.append(SemanticRegion(page_num, [unit], ux0, uy0, ux1, uy1))
                
        regions.extend(active_regions)
    return regions

# ==========================================
# STEP 6E-8: TABLE-LIKE REGION DETECTION
# ==========================================
@dataclass
class RowComponent:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    source_spans: List[PDFSpan]

@dataclass
class TableLikeRegion:
    region: SemanticRegion
    confidence: float
    evidence: List[str]

def _get_row_components(region: SemanticRegion) -> List[List[RowComponent]]:
    """Derives precise geometric components strictly from individual physical PDFLines."""
    all_lines = []
    for u in region.units:
        for line in u.source_lines:
            if line.spans:
                all_lines.append(line)
                
    all_lines.sort(key=lambda l: l.bbox[1])
    
    rows = []
    current_row = []
    current_y0 = None
    current_font_size = 10.0
    
    for line in all_lines:
        ly0 = line.bbox[1]
        font_size = line.spans[-1].size if line.spans[-1].size > 0 else 10.0
        
        if current_y0 is None:
            current_y0 = ly0
            current_font_size = font_size
            
        y_tolerance = max(3.0, current_font_size * 0.5)
        
        if abs(ly0 - current_y0) > y_tolerance:
            if current_row:
                rows.append(sorted(current_row, key=lambda c: c.x0))
            current_row = []
            current_y0 = ly0
            current_font_size = font_size
            
        # Extract components strictly within this single physical line
        comps = []
        curr_group = []
        for span in line.spans:
            if not curr_group:
                curr_group.append(span)
            else:
                gap = span.x0 - curr_group[-1].x1
                if gap > (curr_group[-1].size * 1.5):
                    comps.append(curr_group)
                    curr_group = [span]
                else:
                    curr_group.append(span)
        if curr_group:
            comps.append(curr_group)
            
        # Reconstruct text safely for each geometric component
        for group in comps:
            cx0, cx1 = min(s.x0 for s in group), max(s.x1 for s in group)
            cy0, cy1 = min(s.y0 for s in group), max(s.y1 for s in group)
            
            text = group[0].text
            for i in range(1, len(group)):
                prev_span, curr_span = group[i-1], group[i]
                gap = curr_span.x0 - prev_span.x1
                if gap > (prev_span.size * 0.2):
                    if text.endswith(" ") and curr_span.text.startswith(" "): text += curr_span.text[1:]
                    elif text.endswith(" ") or curr_span.text.startswith(" "): text += curr_span.text
                    else: text += " " + curr_span.text
                else:
                    text += curr_span.text[1:] if (text.endswith(" ") and curr_span.text.startswith(" ")) else curr_span.text
                    
            current_row.append(RowComponent(text.strip(), cx0, cx1, cy0, cy1, group))
            
    if current_row:
        rows.append(sorted(current_row, key=lambda c: c.x0))
        
    return rows

def detect_table_like_regions(regions: List[SemanticRegion]) -> Tuple[List[TableLikeRegion], List[SemanticRegion]]:
    table_like, prose = [], []
    for r in regions:
        rows = _get_row_components(r)
        if len(rows) < 2:
            prose.append(r)
            continue
        
        evidence, confidence = [], 0.0
        
        # Track X positions across DISTINCT rows
        x_rows = defaultdict(set)
        for row_idx, row in enumerate(rows):
            for comp in row:
                bucket = round(comp.x0 / 10) * 10
                x_rows[bucket].add(row_idx)
                
        # A stable column must recur on at least 2 distinct rows
        stable_cols = [x for x, row_ids in x_rows.items() if len(row_ids) >= 2]
        
        if len(stable_cols) >= 2:
            confidence += 0.5
            evidence.append(f"{len(stable_cols)} stable columns detected across >=2 distinct rows.")
            if any(len(row_ids) >= 3 for row_ids in x_rows.values()):
                confidence += 0.2
                evidence.append("Strong multi-row (>3) structural repetition.")
                
        list_markers = sum(1 for row in rows if row and row[0].text.lstrip().startswith(('•', '-', '1.', 'a)')))
        if list_markers > len(rows) * 0.5:
            confidence -= 0.6
            evidence.append("Identified as probable list. Penalized confidence.")
            
        if confidence >= 0.5:
            table_like.append(TableLikeRegion(r, confidence, evidence))
        else:
            prose.append(r)
        
    return table_like, prose

# ==========================================
# STEP 6E-9: TABLE STRUCTURE RECONSTRUCTION
# ==========================================
# ==========================================
# STEP 6E-9: TABLE STRUCTURE RECONSTRUCTION
# ==========================================
# ==========================================
# STEP 6E-9: TABLE STRUCTURE RECONSTRUCTION
# ==========================================
@dataclass
class ReconstructedTable:
    headers: List[str]
    rows: List[List[str]]
    source_region: SemanticRegion

def reconstruct_tables(table_like: List[TableLikeRegion]) -> List[ReconstructedTable]:
    reconstructed = []
    for tlr in table_like:
        rows = _get_row_components(tlr.region)
        if len(rows) < 2:
            continue
        
        # 1. Determine candidate columns from recurring X clusters (must exist on >= 2 distinct rows)
        comp_xs = []
        for row_idx, row in enumerate(rows):
            for comp in row:
                comp_xs.append((comp.x0, row_idx))
                
        comp_xs.sort(key=lambda item: item[0])
        recurring_clusters, curr_cluster_xs, curr_cluster_rows = [], [], set()
        
        for x, row_idx in comp_xs:
            if not curr_cluster_xs or abs(x - statistics.median(curr_cluster_xs)) <= 15.0:
                curr_cluster_xs.append(x)
                curr_cluster_rows.add(row_idx)
            else:
                if len(curr_cluster_rows) >= 2:
                    recurring_clusters.append(statistics.median(curr_cluster_xs))
                curr_cluster_xs, curr_cluster_rows = [x], {row_idx}
                
        if curr_cluster_xs and len(curr_cluster_rows) >= 2:
            recurring_clusters.append(statistics.median(curr_cluster_xs))
            
        # 2. Identify the strongest structural row to capture non-recurring columns (like sparse headers)
        strongest_row = max(rows, key=len) if rows else []
        strongest_xs = [comp.x0 for comp in strongest_row]
        
        # 3. Merge recurring clusters with the strongest row's X positions
        all_candidate_xs = recurring_clusters + strongest_xs
        all_candidate_xs.sort()
        
        cols, curr_merge_xs = [], []
        for x in all_candidate_xs:
            if not curr_merge_xs or abs(x - statistics.median(curr_merge_xs)) <= 15.0:
                curr_merge_xs.append(x)
            else:
                cols.append(statistics.median(curr_merge_xs))
                curr_merge_xs = [x]
        if curr_merge_xs:
            cols.append(statistics.median(curr_merge_xs))
            
        if len(cols) < 2:
            continue 
        
        # 4. Reconstruct rows ensuring blanks remain for missing cells
        raw_rows = []
        for row in rows:
            row_data = [""] * len(cols)
            for comp in row:
                idx = min(range(len(cols)), key=lambda i: abs(cols[i] - comp.x0))
                row_data[idx] = (row_data[idx] + " " + comp.text).strip() if row_data[idx] else comp.text
            raw_rows.append(row_data)
            
        # 5. Header Detection
        headers, final_rows = [], raw_rows
        if len(raw_rows) >= 2 and rows[0]:
            bold_comps = sum(1 for c in rows[0] if any(s.is_bold for s in c.source_spans))
            is_mostly_bold = (bold_comps / len(rows[0])) >= 0.5 if rows[0] else False
            is_short_labels = all(len(cell) < 40 for cell in raw_rows[0])
            second_row_has_numeric = any(any(ch.isdigit() for ch in cell) for cell in raw_rows[1])
            
            if is_mostly_bold or (is_short_labels and second_row_has_numeric):
                headers = raw_rows[0]
                final_rows = raw_rows[1:]
                
        reconstructed.append(ReconstructedTable(headers, final_rows, tlr.region))
        
    return reconstructed

import re

# ==========================================
# STEP 6E-10: LIST DETECTION
# ==========================================

@dataclass
class ReconstructedListItem:
    text: str
    level: int
    source_units: List[ReconstructedTextUnit]


@dataclass
class ReconstructedList:
    list_type: str  # "ordered" or "unordered"
    items: List[ReconstructedListItem]
    page_number: int
    source_region: SemanticRegion


# Supports:
# • item
# - item
# – item
# — item
# * item
UNORDERED_RE = re.compile(
    r'^([•\-–—*])\s+'
)

# Supports:
# 1. item
# 1) item
# a. item
# a) item
# (a) item
# (1) item
# (i) item
# (ii) item
ORDERED_RE = re.compile(
    r'^(\d+\.|\d+\)|[a-zA-Z]\.|[a-zA-Z]\)|\([a-zA-Z0-9]+\))\s+'
)


def detect_lists(
    regions: List[SemanticRegion]
) -> Tuple[List[ReconstructedList], List[SemanticRegion]]:

    lists = []
    non_list_regions = []

    for region in regions:

        current_list_items = []
        current_list_type = None
        base_x0 = None
        leftover_units = []

        for unit in region.units:

            if not unit.source_lines:
                leftover_units.append(unit)
                continue

            text = unit.text.lstrip()

            ux0 = min(
                line.bbox[0]
                for line in unit.source_lines
            )

            is_unordered = bool(
                UNORDERED_RE.match(text)
            )

            is_ordered = bool(
                ORDERED_RE.match(text)
            )

            # ------------------------------------------
            # New list item
            # ------------------------------------------

            if is_unordered or is_ordered:

                if not current_list_items:

                    current_list_type = (
                        "unordered"
                        if is_unordered
                        else "ordered"
                    )

                    base_x0 = ux0

                # Approximate nesting level from indentation.
                # ~15 PDF points = one nesting level.
                level = max(
                    0,
                    int(
                        round(
                            (ux0 - base_x0) / 15.0
                        )
                    )
                )

                if is_unordered:

                    clean_text = UNORDERED_RE.sub(
                        "",
                        text
                    )

                else:

                    clean_text = ORDERED_RE.sub(
                        "",
                        text
                    )

                current_list_items.append(
                    ReconstructedListItem(
                        text=clean_text.strip(),
                        level=level,
                        source_units=[unit]
                    )
                )

            # ------------------------------------------
            # Non-marker line
            # ------------------------------------------

            else:

                # If indented relative to the list base,
                # treat as wrapped continuation.
                if (
                    current_list_items
                    and base_x0 is not None
                    and ux0 > (base_x0 + 10)
                ):

                    current_list_items[-1].text += (
                        " " + text.strip()
                    )

                    # Preserve provenance of continuation.
                    current_list_items[
                        -1
                    ].source_units.append(unit)

                else:

                    # Close current list.
                    if current_list_items:

                        lists.append(
                            ReconstructedList(
                                list_type=current_list_type,
                                items=current_list_items,
                                page_number=region.page_number,
                                source_region=region
                            )
                        )

                        current_list_items = []
                        current_list_type = None
                        base_x0 = None

                    leftover_units.append(unit)

        # ----------------------------------------------
        # Flush list remaining at end of region
        # ----------------------------------------------

        if current_list_items:

            lists.append(
                ReconstructedList(
                    list_type=current_list_type,
                    items=current_list_items,
                    page_number=region.page_number,
                    source_region=region
                )
            )

        # ----------------------------------------------
        # Preserve content that wasn't classified as list
        # ----------------------------------------------

        if leftover_units:

            # Entire region was non-list.
            if len(leftover_units) == len(region.units):

                non_list_regions.append(region)

            else:

                # Reconstruct region bbox from remaining
                # non-list units.
                rx0 = min(
                    min(
                        line.bbox[0]
                        for line in unit.source_lines
                    )
                    for unit in leftover_units
                )

                ry0 = min(
                    min(
                        line.bbox[1]
                        for line in unit.source_lines
                    )
                    for unit in leftover_units
                )

                rx1 = max(
                    max(
                        line.bbox[2]
                        for line in unit.source_lines
                    )
                    for unit in leftover_units
                )

                ry1 = max(
                    max(
                        line.bbox[3]
                        for line in unit.source_lines
                    )
                    for unit in leftover_units
                )

                non_list_regions.append(
                    SemanticRegion(
                        page_number=region.page_number,
                        units=leftover_units,
                        x0=rx0,
                        y0=ry0,
                        x1=rx1,
                        y1=ry1
                    )
                )

    return lists, non_list_regions


# ==========================================
# STEP 6E-11: HEADING DETECTION
# ==========================================

@dataclass
class ReconstructedHeading:
    text: str
    level: str  # "H1", "H2", "H3", "H4"
    page_number: int
    source_unit: ReconstructedTextUnit


def _get_document_median_font(
    units: List[ReconstructedTextUnit]
) -> float:

    sizes = []

    for unit in units:

        for line in unit.source_lines:

            for span in line.spans:

                if span.size > 0:
                    sizes.append(span.size)

    return (
        statistics.median(sizes)
        if sizes
        else 10.0
    )


def detect_headings(
    units: List[ReconstructedTextUnit]
) -> Tuple[
    List[ReconstructedHeading],
    List[ReconstructedTextUnit]
]:

    headings = []
    body_text = []

    if not units:
        return headings, body_text

    median_size = _get_document_median_font(
        units
    )

    for unit in units:

        if not unit.source_lines:
            body_text.append(unit)
            continue

        text = unit.text.strip()

        # Obvious body-text safeguards.
        if (
            not text
            or len(text) > 100
            or text.endswith(".")
        ):

            body_text.append(unit)
            continue

        max_size = max(
            (
                span.size
                for line in unit.source_lines
                for span in line.spans
            ),
            default=10.0
        )

        is_bold = any(
            span.is_bold
            for line in unit.source_lines
            for span in line.spans
        )

        level = None

        if max_size >= median_size * 1.5:

            level = "H1"

        elif max_size >= median_size * 1.2:

            level = "H2"

        elif (
            max_size >= median_size * 1.05
            and is_bold
        ):

            level = "H3"

        elif (
            max_size >= median_size
            and is_bold
            and len(text) < 60
        ):

            level = "H4"

        if level:

            headings.append(
                ReconstructedHeading(
                    text=text,
                    level=level,
                    page_number=(
                        unit.source_lines[0]
                        .page_number
                    ),
                    source_unit=unit
                )
            )

        else:

            body_text.append(unit)

    return headings, body_text


# ==========================================
# STEP 6E-12: IMAGE EXTRACTION
# ==========================================

@dataclass
class ExtractedImage:
    page_number: int
    bbox: Tuple[
        float,
        float,
        float,
        float
    ]
    width: float
    height: float


def extract_images(
    file_path: str
) -> List[ExtractedImage]:

    """
    Detect image blocks exposed by PyMuPDF.

    This stage only preserves image position,
    dimensions and page provenance.

    It does NOT perform OCR, caption generation,
    or image understanding.
    """

    doc = pymupdf.open(file_path)

    images = []

    for page_idx in range(len(doc)):

        page = doc[page_idx]

        dict_data = page.get_text("dict")

        for block in dict_data.get(
            "blocks",
            []
        ):

            # PyMuPDF:
            # type 0 = text
            # type 1 = image
            if block.get("type") != 1:
                continue

            bbox = block.get(
                "bbox",
                (
                    0.0,
                    0.0,
                    0.0,
                    0.0
                )
            )

            images.append(
                ExtractedImage(
                    page_number=page_idx + 1,
                    bbox=(
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3])
                    ),
                    width=float(
                        block.get(
                            "width",
                            0
                        )
                    ),
                    height=float(
                        block.get(
                            "height",
                            0
                        )
                    )
                )
            )

    doc.close()

    return images

# ==========================================
# STEP 6F: PDF -> NORMALIZED DOCUMENT
# ==========================================

import os
import hashlib

from src.schemas import (
    NormalizedDocument,
    DocumentMetadata,
    Section,
    TextBlock,
    TableBlock,
    ListBlock,
    ListItem,
    ImageBlock,
)


def convert_pdf_to_normalized_document(
    file_path: str
) -> NormalizedDocument:
    """
    Runs the complete PDF parsing pipeline from 6E-1 to 6E-12
    and converts the result into the locked NormalizedDocument schema.
    """

    # ======================================================
    # 1. BASE PDF PIPELINE
    # ======================================================

    raw_lines = parse_pdf_to_lines(
        file_path
    )

    hyphen_units = repair_hyphenation(
        raw_lines
    )

    filtered = filter_edge_noise(
        hyphen_units
    )

    regions = detect_semantic_regions(
        filtered.kept_units
    )

    # ======================================================
    # 2. STRUCTURAL CLASSIFICATION
    #
    # Priority:
    #
    # List
    # -> Table
    # -> Heading
    # -> Body Text
    # ======================================================

    # ------------------------------------------------------
    # Lists first
    # ------------------------------------------------------

    detected_lists, non_list_regions = detect_lists(
        regions
    )

    # ------------------------------------------------------
    # Tables only see content not already classified as list
    # ------------------------------------------------------

    table_like_regions, prose_regions = (
        detect_table_like_regions(
            non_list_regions
        )
    )

    reconstructed_tables = reconstruct_tables(
        table_like_regions
    )

    # ------------------------------------------------------
    # Gather definite prose units
    # ------------------------------------------------------

    non_table_units = [
        unit
        for region in prose_regions
        for unit in region.units
    ]

    # ------------------------------------------------------
    # IMPORTANT:
    #
    # SemanticRegion is unhashable because it contains lists.
    # Therefore compare object identity using id().
    # ------------------------------------------------------

    reconstructed_table_region_ids = {
        id(table.source_region)
        for table in reconstructed_tables
    }

    # Table-like regions that failed reconstruction should
    # return to the heading/body pipeline rather than vanish.
    for table_like_region in table_like_regions:

        if (
            id(table_like_region.region)
            not in reconstructed_table_region_ids
        ):

            non_table_units.extend(
                table_like_region.region.units
            )

    # ------------------------------------------------------
    # Headings after lists/tables
    # ------------------------------------------------------

    detected_headings, body_text = detect_headings(
        non_table_units
    )

    # ------------------------------------------------------
    # Images handled independently
    # ------------------------------------------------------

    images = extract_images(
        file_path
    )

    # ======================================================
    # 3. MERGE EVERYTHING BACK INTO DOCUMENT ORDER
    # ======================================================

    sortable_items = []

    # ------------------------------------------------------
    # Lists
    # ------------------------------------------------------

    for detected_list in detected_lists:

        sortable_items.append(
            (
                detected_list.page_number,
                detected_list.source_region.y0,
                detected_list.source_region.x0,
                "list",
                detected_list,
            )
        )

    # ------------------------------------------------------
    # Tables
    # ------------------------------------------------------

    for table in reconstructed_tables:

        sortable_items.append(
            (
                table.source_region.page_number,
                table.source_region.y0,
                table.source_region.x0,
                "table",
                table,
            )
        )

    # ------------------------------------------------------
    # Headings
    # ------------------------------------------------------

    for heading in detected_headings:

        if not heading.source_unit.source_lines:
            continue

        heading_y0 = min(
            line.bbox[1]
            for line in heading.source_unit.source_lines
        )

        heading_x0 = min(
            line.bbox[0]
            for line in heading.source_unit.source_lines
        )

        sortable_items.append(
            (
                heading.page_number,
                heading_y0,
                heading_x0,
                "heading",
                heading,
            )
        )

    # ------------------------------------------------------
    # Body text
    # ------------------------------------------------------

    for unit in body_text:

        if not unit.source_lines:
            continue

        body_y0 = min(
            line.bbox[1]
            for line in unit.source_lines
        )

        body_x0 = min(
            line.bbox[0]
            for line in unit.source_lines
        )

        page_number = unit.source_lines[
            0
        ].page_number

        sortable_items.append(
            (
                page_number,
                body_y0,
                body_x0,
                "body",
                unit,
            )
        )

    # ------------------------------------------------------
    # Images
    # ------------------------------------------------------

    for image in images:

        sortable_items.append(
            (
                image.page_number,
                image.bbox[1],
                image.bbox[0],
                "image",
                image,
            )
        )

    # Sort by:
    #
    # page
    # -> vertical position
    # -> horizontal position
    sortable_items.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        )
    )

    # ======================================================
    # 4. DOCUMENT METADATA
    # ======================================================

    # ------------------------------------------------------
    # Title
    # ------------------------------------------------------

    title = None

    # Prefer first H1
    h1_headings = [
        item[4]
        for item in sortable_items
        if (
            item[3] == "heading"
            and item[4].level == "H1"
        )
    ]

    if h1_headings:

        title = h1_headings[0].text

    else:

        # Otherwise use first detected heading
        all_headings = [
            item[4]
            for item in sortable_items
            if item[3] == "heading"
        ]

        if all_headings:

            title = all_headings[0].text

    # Final fallback = filename
    if not title:

        title = os.path.splitext(
            os.path.basename(
                file_path
            )
        )[0]

    # ------------------------------------------------------
    # Enterprise
    # ------------------------------------------------------

    path_lower = file_path.lower()

    if "aventro" in path_lower:

        enterprise = "Aventro Motors"

    elif "cendara" in path_lower:

        enterprise = "Cendara University"

    elif (
        "cloudway" in path_lower
        or "cloudway-24" in path_lower
    ):

        enterprise = "CloudWay-24"

    elif "velvera" in path_lower:

        enterprise = "Velvera Technologies"

    elif (
        "zx bank" in path_lower
        or "zx_bank" in path_lower
        or "zx-bank" in path_lower
    ):

        enterprise = "ZX Bank"

    else:

        enterprise = "Unknown"

    # ------------------------------------------------------
    # Stable deterministic document ID
    # ------------------------------------------------------

    identity_string = (
        enterprise
        + "::"
        + os.path.basename(
            file_path
        )
    )

    document_id = hashlib.sha256(
        identity_string.encode(
            "utf-8"
        )
    ).hexdigest()

    metadata = DocumentMetadata(
        enterprise=enterprise,
        source_filename=os.path.basename(
            file_path
        ),
        source_format="pdf",
        document_version=None,
        author=None,
        date=None,
        access_groups=[],
    )

    # ======================================================
    # 5. NESTED LIST CONVERSION
    # ======================================================

    def build_nested_list(
        flat_items,
        list_type: str,
        page_number: int,
    ):
        """
        Converts:

        level 0
        level 1
        level 2

        into the locked schema:

        ListItem
            -> sub_lists: List[ListBlock]
        """

        root_items = []

        # Stack stores the most recent ListItem at each
        # nesting depth.
        stack = []

        for reconstructed_item in flat_items:

            new_item = ListItem(
                text=reconstructed_item.text,
                sub_lists=[],
            )

            level = max(
                0,
                reconstructed_item.level,
            )

            # ------------------------------------------------
            # Root list item
            # ------------------------------------------------

            if level == 0:

                root_items.append(
                    new_item
                )

                stack = [
                    new_item
                ]

                continue

            # ------------------------------------------------
            # Nested item
            # ------------------------------------------------

            # Prevent impossible indentation jumps.
            #
            # Example:
            # current stack depth = 1
            # item says level 4
            #
            # Attach it to the deepest valid parent.
            parent_index = min(
                level - 1,
                len(stack) - 1,
            )

            if parent_index < 0:

                root_items.append(
                    new_item
                )

                stack = [
                    new_item
                ]

                continue

            parent_item = stack[
                parent_index
            ]

            # The locked schema requires:
            #
            # ListItem.sub_lists
            #     -> List[ListBlock]
            #
            # NOT List[ListItem].
            if not parent_item.sub_lists:

                parent_item.sub_lists.append(
                    ListBlock(
                        list_type=list_type,
                        items=[],
                        page_number=page_number,
                    )
                )

            nested_block = (
                parent_item.sub_lists[-1]
            )

            nested_block.items.append(
                new_item
            )

            # Update nesting stack.
            stack = stack[
                : parent_index + 1
            ]

            stack.append(
                new_item
            )

        return root_items

    # ======================================================
    # 6. BUILD SECTIONS
    # ======================================================

    sections = []

    current_hierarchy = []
    current_blocks = []

    def flush_section():
        nonlocal current_blocks

        if not current_blocks:
            return

        sections.append(
            Section(
                hierarchy=list(
                    current_hierarchy
                ),
                blocks=current_blocks,
            )
        )

        current_blocks = []

    # ======================================================
    # 7. PROCESS ORDERED STRUCTURES
    # ======================================================

    for (
        _page,
        _y,
        _x,
        item_type,
        obj,
    ) in sortable_items:

        # --------------------------------------------------
        # Heading
        # --------------------------------------------------

        if item_type == "heading":

            flush_section()

            try:
                heading_level = int(
                    obj.level[1:]
                )

            except (
                ValueError,
                IndexError,
            ):

                heading_level = 1

            heading_level = max(
                1,
                min(
                    heading_level,
                    4,
                ),
            )

            # Example:
            #
            # H1 A
            # H2 B
            # H3 C
            #
            # current:
            # ["A", "B", "C"]
            #
            # new H2:
            # ["A", new]
            current_hierarchy = (
                current_hierarchy[
                    : heading_level - 1
                ]
            )

            current_hierarchy.append(
                obj.text
            )

        # --------------------------------------------------
        # Body Text
        # --------------------------------------------------

        elif item_type == "body":

            text = obj.text.strip()

            if not text:
                continue

            if not obj.source_lines:
                continue

            current_blocks.append(
                TextBlock(
                    text=text,
                    page_number=(
                        obj.source_lines[
                            0
                        ].page_number
                    ),
                )
            )

        # --------------------------------------------------
        # List
        # --------------------------------------------------

        elif item_type == "list":

            if not obj.items:
                continue

            items_schema = build_nested_list(
                flat_items=obj.items,
                list_type=obj.list_type,
                page_number=obj.page_number,
            )

            if not items_schema:
                continue

            current_blocks.append(
                ListBlock(
                    list_type=obj.list_type,
                    items=items_schema,
                    page_number=obj.page_number,
                )
            )

        # --------------------------------------------------
        # Table
        # --------------------------------------------------

        elif item_type == "table":

            if (
                not obj.headers
                and not obj.rows
            ):
                continue

            # Remove completely empty rows.
            clean_rows = [
                row
                for row in obj.rows
                if any(
                    str(cell).strip()
                    for cell in row
                )
            ]

            clean_headers = [
                str(header).strip()
                for header in obj.headers
            ]

            if (
                not clean_headers
                and not clean_rows
            ):
                continue

            current_blocks.append(
                TableBlock(
                    headers=clean_headers,
                    rows=clean_rows,
                    page_number=(
                        obj.source_region
                        .page_number
                    ),
                )
            )

        # --------------------------------------------------
        # Image
        # --------------------------------------------------

        elif item_type == "image":

            current_blocks.append(
                ImageBlock(
                    alt_text=None,
                    caption=None,
                    page_number=(
                        obj.page_number
                    ),
                )
            )

    # Flush final remaining section.
    flush_section()

    # ======================================================
    # 8. HANDLE DOCUMENTS WITH NO BLOCKS
    # ======================================================

    # Normally this should not happen because all 236 PDFs
    # have extractable text.
    #
    # But preserve a valid document instead of crashing.
    if not sections:

        sections = [
            Section(
                hierarchy=[],
                blocks=[],
            )
        ]

    # ======================================================
    # 9. BUILD LOCKED PYDANTIC DOCUMENT
    # ======================================================

    normalized_document = NormalizedDocument(
        document_id=document_id,
        title=title,
        metadata=metadata,
        sections=sections,
    )

    return normalized_document