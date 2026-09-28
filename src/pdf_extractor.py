"""
PDF text layer inspection, multi-signal routing, rendering,
and hybrid page handling module for Local Thai OCR Web.
"""

import os
import re
import math
import fitz  # PyMuPDF
from PIL import Image, ImageStat
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from .geometry import Rect, AffineTransform


@dataclass
class PageRoutingResult:
    page_id: int
    decision: str  # 'direct_text', 'ocr_image', 'hybrid', 'blank'
    reason: str
    text_length: int
    printable_ratio: float
    thai_char_count: int
    broken_encoding_detected: bool
    image_count: int
    image_area_ratio: float
    is_visually_blank: bool


def is_thai_char(c: str) -> bool:
    return "\u0e00" <= c <= "\u0e7f"


def check_thai_encoding_quality(text: str) -> Tuple[bool, str]:
    """
    Check for broken CID fonts / ToUnicode mapping errors in Thai text.
    Returns (is_broken, reason).
    """
    if not text:
        return False, "empty"

    # Replacement characters or null bytes
    if "\ufffd" in text or "\x00" in text:
        return True, "contains replacement character U+FFFD or null bytes"

    # Check for private use area characters (frequently used by faulty PDF generators)
    pua_count = sum(1 for c in text if "\ue000" <= c <= "\uf8ff")
    if pua_count > max(2, len(text) * 0.05):
        return True, f"high private use area characters count: {pua_count}"

    # Isolated floating upper/lower vowels or tone marks without base consonants
    # E.g., multiple consecutive floating tone marks or vowel starting lines improperly
    floating_tones = re.findall(r"[\u0e48-\u0e4e]{2,}", text)
    if len(floating_tones) > 5:
        return True, "excessive consecutive floating tone marks indicating font encoding corruption"

    return False, "clean"


def check_visual_blank(image: Image.Image, threshold_std: float = 2.0) -> bool:
    """
    Check if an image is visually blank (e.g. solid white/single color).
    """
    if image.mode != "L":
        gray = image.convert("L")
    else:
        gray = image
    min_v, max_v = gray.getextrema()
    if (max_v - min_v) < 5:
        return True
    stat = ImageStat.Stat(gray)
    try:
        var = stat.var[0]
        if var <= 0:
            return True
        std_dev = math.sqrt(max(0.0, var))
        return std_dev < threshold_std
    except Exception:
        return False


def inspect_pdf_page(page: fitz.Page, page_id: int, dpi: int = 300) -> PageRoutingResult:
    """
    Multi-signal analysis of PDF page to determine optimal routing:
    - direct_text (clean native text)
    - ocr_image (scanned or corrupted text layer)
    - hybrid (native text + embedded graphics requiring OCR)
    - blank (completely empty page)
    """
    text = page.get_text()
    non_ws_chars = len(re.sub(r"\s+", "", text))
    thai_chars = sum(1 for c in text if is_thai_char(c))

    # Font encoding check
    is_broken, broken_reason = check_thai_encoding_quality(text)

    # Images inspection
    images = page.get_images()
    page_rect = page.rect
    page_area = max(1.0, page_rect.width * page_rect.height)

    # Compute bounding boxes of embedded images
    image_rects = []
    for img_info in images:
        xref = img_info[0]
        rects = page.get_image_rects(xref)
        for r in rects:
            image_rects.append(Rect(r.x0, r.y0, r.x1, r.y1))

    total_img_area = sum(r.area for r in image_rects)
    image_area_ratio = min(1.0, total_img_area / page_area)

    # Check visual blank if text is empty
    is_visually_blank = False
    if non_ws_chars == 0:
        rendered = render_pdf_page_to_image(page, dpi=100)
        is_visually_blank = check_visual_blank(rendered)

    # Routing Decision Logic
    if non_ws_chars == 0:
        if is_visually_blank:
            decision = "blank"
            reason = "Page has 0 text characters and visual background is completely blank/white"
        else:
            decision = "ocr_image"
            reason = f"Page has no text layer but contains visual content ({len(images)} images, area ratio {image_area_ratio:.2f})"
    elif is_broken:
        decision = "ocr_image"
        reason = f"Native text layer has corrupted/unmapped encoding ({broken_reason}), routing to OCR"
    elif len(images) > 0 and image_area_ratio >= 0.4 and non_ws_chars < 15:
        # Scanned page with trivial watermark/artifact text (e.g. scanner stamp like 'kkr')
        decision = "ocr_image"
        reason = f"Page is dominated by visual image (area ratio {image_area_ratio:.2f}) with minimal text artifact ({non_ws_chars} chars), routing to OCR"
    elif len(images) > 0 and image_area_ratio >= 0.15 and non_ws_chars >= 15:
        # Both significant native text and significant image area
        decision = "hybrid"
        reason = f"Page has valid native text ({non_ws_chars} chars) and significant image regions ({len(images)} images, area ratio {image_area_ratio:.2f})"
    else:
        # Clean native text
        decision = "direct_text"
        reason = f"Page has clean native vector text layer ({non_ws_chars} chars, {thai_chars} Thai chars, 0 font corruption)"

    printable_ratio = non_ws_chars / max(1, len(text))

    return PageRoutingResult(
        page_id=page_id,
        decision=decision,
        reason=reason,
        text_length=len(text),
        printable_ratio=round(printable_ratio, 4),
        thai_char_count=thai_chars,
        broken_encoding_detected=is_broken,
        image_count=len(images),
        image_area_ratio=round(image_area_ratio, 4),
        is_visually_blank=is_visually_blank,
    )


def render_pdf_page_to_image(page: fitz.Page, dpi: int = 300) -> Image.Image:
    """
    Render PDF page to PIL Image at specified DPI.
    """
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img


def extract_native_text_blocks(page: fitz.Page, dpi: int = 300) -> List[Dict[str, Any]]:
    """
    Extract native vector text blocks from PDF page, converting coordinates
    from points (1/72 inch) to reference image pixels at given DPI.
    """
    scale = dpi / 72.0
    raw_blocks = page.get_text("blocks")
    # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
    # block_type 0 = text, 1 = image

    blocks = []
    for b in raw_blocks:
        x0, y0, x1, y1, text, block_no, b_type = b
        if b_type != 0 or not text.strip():
            continue

        # Scale bbox to reference image pixels
        px0 = x0 * scale
        py0 = y0 * scale
        px1 = x1 * scale
        py1 = y1 * scale

        quad = [
            round(px0, 2), round(py0, 2),
            round(px1, 2), round(py0, 2),
            round(px1, 2), round(py1, 2),
            round(px0, 2), round(py1, 2),
        ]

        # Extract lines within block
        lines = []
        raw_lines = text.split("\n")
        # Estimate vertical line height
        total_lines = max(1, len([l for l in raw_lines if l.strip()]))
        line_h = (py1 - py0) / total_lines

        curr_y = py0
        line_idx = 0
        for l_text in raw_lines:
            if not l_text.strip():
                continue
            line_quad = [
                round(px0, 2), round(curr_y, 2),
                round(px1, 2), round(curr_y, 2),
                round(px1, 2), round(curr_y + line_h, 2),
                round(px0, 2), round(curr_y + line_h, 2),
            ]
            lines.append({
                "line_index": line_idx,
                "text": l_text,
                "bbox": {
                    "x1": line_quad[0], "y1": line_quad[1],
                    "x2": line_quad[2], "y2": line_quad[3],
                    "x3": line_quad[4], "y3": line_quad[5],
                    "x4": line_quad[6], "y4": line_quad[7],
                },
                "words": []
            })
            curr_y += line_h
            line_idx += 1

        blocks.append({
            "block_id": f"p{page.number + 1}_b{block_no}",
            "source": "pdf_text",
            "confidence": None,
            "bbox": {
                "x1": quad[0], "y1": quad[1],
                "x2": quad[2], "y2": quad[3],
                "x3": quad[4], "y3": quad[5],
                "x4": quad[6], "y4": quad[7],
            },
            "rect": Rect(px0, py0, px1, py1),
            "text": text.strip(),
            "lines": lines,
        })

    return blocks
