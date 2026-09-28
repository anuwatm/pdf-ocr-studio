"""
Text assembly, reading order, column detection, table formatting,
and source mapping module for Local Thai OCR Web.
"""

from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from .geometry import Rect, quad_to_rect


@dataclass
class CharSpanMapping:
    start: int
    end: int
    page_id: int
    block_id: str
    line_index: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "page_id": self.page_id,
            "block_id": self.block_id,
            "line_index": self.line_index,
            "text": self.text,
        }


def sort_blocks_reading_order(blocks: List[Dict[str, Any]], column_gap_threshold: float = 40.0) -> List[Dict[str, Any]]:
    """
    Sort text blocks in natural reading order (top-to-bottom, left-to-right,
    supporting multi-column layouts when present).
    """
    if not blocks:
        return []

    # Assign rect if not present
    parsed = []
    for b in blocks:
        if "rect" not in b and "bbox" in b:
            bb = b["bbox"]
            quad = [bb["x1"], bb["y1"], bb["x2"], bb["y2"], bb["x3"], bb["y3"], bb["x4"], bb["y4"]]
            b["rect"] = quad_to_rect(quad)
        parsed.append(b)

    # Detect multi-column separation
    # Find bounding box of all blocks
    min_x = min(b["rect"].x0 for b in parsed)
    max_x = max(b["rect"].x1 for b in parsed)
    page_w = max_x - min_x

    # Check if there is a distinct vertical column split
    # For standard documents, sort primarily by top (y0), with horizontal tolerance
    # Group into bands or columns
    def block_sort_key(b):
        r = b["rect"]
        # Quantize y to 15-pixel band to handle slight misalignment on same row
        return (round(r.y0 / 15.0), r.x0)

    # Check if there are distinct columns (e.g. 2 columns with clear vertical divider)
    # Check if page has left and right column clusters
    mid_x = min_x + page_w / 2.0
    left_blocks = [b for b in parsed if b["rect"].x1 <= mid_x]
    right_blocks = [b for b in parsed if b["rect"].x0 >= mid_x]

    # If > 80% of blocks fall cleanly into left and right with no horizontal overlap
    if len(left_blocks) + len(right_blocks) >= len(parsed) * 0.85 and len(left_blocks) >= 2 and len(right_blocks) >= 2:
        # Multi-column reading order: Left column top-to-bottom, then Right column top-to-bottom
        left_sorted = sorted(left_blocks, key=lambda b: (b["rect"].y0, b["rect"].x0))
        right_sorted = sorted(right_blocks, key=lambda b: (b["rect"].y0, b["rect"].x0))
        return left_sorted + right_sorted
    else:
        # Single column or flowing layout: top-to-bottom, left-to-right
        return sorted(parsed, key=block_sort_key)


def detect_and_format_table_lines(lines: List[Dict[str, Any]], x_tolerance: float = 30.0) -> List[str]:
    """
    Format lines that belong to table rows using tab '\\t' between columns.
    """
    if not lines:
        return []

    # Check if lines have word-level bboxes forming distinct columns
    formatted_lines = []
    for line in lines:
        words = line.get("words", [])
        if len(words) >= 2:
            # Sort words by x
            words_sorted = sorted(words, key=lambda w: w["bbox"]["x1"] if isinstance(w.get("bbox"), dict) else 0)
            # If large horizontal gap between words, insert tab '\t'
            row_parts = []
            curr_part = []
            prev_x1 = None
            for w in words_sorted:
                w_text = w.get("text", "")
                bbox = w.get("bbox", {})
                w_x0 = bbox.get("x1", 0) if isinstance(bbox, dict) else 0
                w_x1 = bbox.get("x2", 0) if isinstance(bbox, dict) else 0

                if prev_x1 is not None and (w_x0 - prev_x1) > x_tolerance:
                    row_parts.append(" ".join(curr_part))
                    curr_part = [w_text]
                else:
                    curr_part.append(w_text)
                prev_x1 = w_x1

            if curr_part:
                row_parts.append(" ".join(curr_part))

            if len(row_parts) >= 2:
                formatted_lines.append("\t".join(row_parts))
                continue

        formatted_lines.append(line.get("text", ""))

    return formatted_lines


def assemble_page_text(
    page_id: int,
    blocks: List[Dict[str, Any]],
    preserve_line_breaks: bool = True
) -> Tuple[str, List[CharSpanMapping]]:
    """
    Assemble page blocks into coherent raw text string, enforcing Thai line wrapping
    rules (preserve newline when unsure), and recording exact character span mappings.
    """
    sorted_blocks = sort_blocks_reading_order(blocks)
    assembled_parts = []
    mappings: List[CharSpanMapping] = []
    current_char_offset = 0

    for b_idx, block in enumerate(sorted_blocks):
        block_id = block.get("block_id", f"p{page_id}_b{b_idx}")
        lines = block.get("lines", [])

        # If block has lines, process line by line
        if lines:
            for l_idx, line in enumerate(lines):
                l_text = line.get("text", "").strip()
                if not l_text:
                    continue

                # Add newline before line if not at start of block
                if l_idx > 0:
                    assembled_parts.append("\n")
                    current_char_offset += 1

                start_pos = current_char_offset
                assembled_parts.append(l_text)
                current_char_offset += len(l_text)
                end_pos = current_char_offset

                mappings.append(
                    CharSpanMapping(
                        start=start_pos,
                        end=end_pos,
                        page_id=page_id,
                        block_id=block_id,
                        line_index=l_idx,
                        text=l_text,
                    )
                )
        else:
            # Fallback to block text
            b_text = block.get("text", "").strip()
            if b_text:
                start_pos = current_char_offset
                assembled_parts.append(b_text)
                current_char_offset += len(b_text)
                end_pos = current_char_offset

                mappings.append(
                    CharSpanMapping(
                        start=start_pos,
                        end=end_pos,
                        page_id=page_id,
                        block_id=block_id,
                        line_index=0,
                        text=b_text,
                    )
                )

        # Paragraph separator between distinct blocks (double newline)
        if b_idx < len(sorted_blocks) - 1:
            assembled_parts.append("\n\n")
            current_char_offset += 2

    page_text = "".join(assembled_parts)
    return page_text, mappings
