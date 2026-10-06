"""Phase 8.1 structured layout model and deterministic Text/HTML exports."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import statistics
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.file_utils import atomic_write_json, atomic_write_text


LAYOUT_SCHEMA_VERSION = "1.0.0"
MAX_LAYOUT_BLOCKS = 100_000
MAX_TABLE_CELLS = 20_000
LIST_MARKER = re.compile(r"^\s*(?P<marker>(?:[-*•▪◦])|(?:\d{1,3}[.)]))\s+(?P<text>.+)$")


def _bbox_from_rect(rect: Iterable[float], scale: float = 1.0) -> Dict[str, float]:
    x0, y0, x1, y1 = [float(value) * scale for value in rect]
    return {
        "x1": round(x0, 2), "y1": round(y0, 2),
        "x2": round(x1, 2), "y2": round(y0, 2),
        "x3": round(x1, 2), "y3": round(y1, 2),
        "x4": round(x0, 2), "y4": round(y1, 2),
    }


def _rect_from_bbox(bbox: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs = [float(bbox.get(key, 0)) for key in ("x1", "x2", "x3", "x4")]
    ys = [float(bbox.get(key, 0)) for key in ("y1", "y2", "y3", "y4")]
    return min(xs), min(ys), max(xs), max(ys)


def _inside_table(block: Dict[str, Any], table_rects: List[Tuple[float, float, float, float]]) -> bool:
    bbox = block.get("bbox")
    if not isinstance(bbox, dict):
        return False
    x0, y0, x1, y1 = _rect_from_bbox(bbox)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return any(tx0 <= cx <= tx1 and ty0 <= cy <= ty1 for tx0, ty0, tx1, ty1 in table_rects)


def _plain_blocks(page_id: int, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    layout: List[Dict[str, Any]] = []
    pending_list: Optional[Dict[str, Any]] = None
    sizes = []
    for source_block in blocks:
        for line in source_block.get("lines") or []:
            size = float((line.get("style") or {}).get("size_median", 0) or 0)
            if size > 0 and str(line.get("text") or "").strip():
                sizes.append(size)
    body_size = statistics.median(sizes) if sizes else 0.0
    heading_seen = False
    for index, source_block in enumerate(blocks):
        block_id = str(source_block.get("block_id") or f"p{page_id}_b{index}")
        source = str(source_block.get("source") or "legacy")
        confidence = source_block.get("confidence")
        lines = source_block.get("lines") or []
        texts = [str(line.get("text") or "").strip() for line in lines]
        texts = [value for value in texts if value]
        if not texts and str(source_block.get("text") or "").strip():
            texts = [str(source_block["text"]).strip()]
        for line_index, text in enumerate(texts):
            match = LIST_MARKER.match(text)
            if match:
                marker = match.group("marker")
                list_type = "ordered" if marker[0].isdigit() else "unordered"
                if not pending_list or pending_list["list_type"] != list_type:
                    pending_list = {
                        "block_id": f"{block_id}_list",
                        "type": "list",
                        "list_type": list_type,
                        "bbox": source_block.get("bbox"),
                        "source": source,
                        "confidence": confidence,
                        "evidence": ["marker", "indent", "source_bbox"],
                        "items": [],
                    }
                    layout.append(pending_list)
                pending_list["items"].append({
                    "item_id": f"{block_id}_li{line_index}",
                    "marker": marker,
                    "text": match.group("text"),
                    "bbox": (lines[line_index].get("bbox") if line_index < len(lines) else source_block.get("bbox")),
                    "source_text": text,
                    "indent": (_rect_from_bbox((lines[line_index].get("bbox") or source_block.get("bbox") or {}))[0]
                               if line_index < len(lines) else None),
                })
                continue

            pending_list = None
            style = lines[line_index].get("style", {}) if line_index < len(lines) else source_block.get("style", {})
            size = float((style or {}).get("size_median", 0) or 0)
            bold = float((style or {}).get("bold_ratio", 0) or 0)
            heading = bool(body_size and len(text) <= 100 and size >= body_size * 1.2
                           and (bold >= 0.6 or size >= body_size * 1.35))
            block_type = ("h1" if not heading_seen else "h2") if heading else "paragraph"
            heading_seen = heading_seen or heading
            layout.append({
                "block_id": f"{block_id}_l{line_index}",
                "type": block_type,
                "text": text,
                "bbox": (lines[line_index].get("bbox") if line_index < len(lines) else source_block.get("bbox")),
                "source": source,
                "confidence": confidence,
                "evidence": (["font_size", "font_weight"] if heading else ["legacy_block_fallback"]),
                "style": style or {},
            })
    return layout


def _promote_tab_tables(page_id: int, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Promote only consecutive tab rows; a lone numbered row remains a paragraph."""
    result: List[Dict[str, Any]] = []
    index = 0
    table_index = 0
    while index < len(blocks):
        run: List[Dict[str, Any]] = []
        cursor = index
        while cursor < len(blocks) and blocks[cursor].get("type") == "paragraph" and "\t" in str(blocks[cursor].get("text", "")):
            run.append(blocks[cursor])
            cursor += 1
        widths = [len(str(block.get("text", "")).split("\t")) for block in run]
        if len(run) >= 2 and max(widths, default=0) >= 2:
            column_count = max(widths)
            rows = []
            unresolved = []
            for row_index, block in enumerate(run):
                values = str(block.get("text", "")).split("\t")
                values.extend([""] * (column_count - len(values)))
                cells = []
                for column_index, value in enumerate(values):
                    cells.append({
                        "cell_id": f"p{page_id}_tab{table_index}_r{row_index}_c{column_index}",
                        "row_index": row_index, "column_index": column_index,
                        "rowspan": 1, "colspan": 1,
                        "text": value, "source_text": value, "bbox": None,
                        "source": block.get("source", "ocr"),
                        "confidence": block.get("confidence"),
                        "evidence": ["tab_stop_inference"], "unresolved": True,
                    })
                    unresolved.append({"row_index": row_index, "column_index": column_index,
                                       "reason": "cell_bbox_unavailable_for_tab_stop_table"})
                rows.append({"row_index": row_index, "cells": cells})
            result.append({
                "block_id": f"p{page_id}_tab_table_{table_index}", "type": "table",
                "bbox": run[0].get("bbox"), "source": "tab_stop_inference", "confidence": None,
                "evidence": ["consecutive_tab_rows"], "header_rows": 0,
                "row_count": len(rows), "column_count": column_count,
                "rows": rows, "unresolved": unresolved,
            })
            table_index += 1
            index = cursor
        else:
            result.append(blocks[index])
            index += 1
    return result


def _cluster_boundaries(values: Iterable[float], tolerance: float = 1.0) -> List[float]:
    clusters: List[List[float]] = []
    for value in sorted(float(item) for item in values):
        if not clusters or abs(value - (sum(clusters[-1]) / len(clusters[-1]))) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _nearest_boundary(boundaries: List[float], value: float) -> int:
    return min(range(len(boundaries)), key=lambda index: abs(boundaries[index] - float(value)))


def extract_pdf_vector_tables(page: Any, dpi: int = 300) -> List[Dict[str, Any]]:
    """Extract vector tables with PyMuPDF. Unsupported merges remain explicit."""
    scale = float(dpi) / 72.0
    result: List[Dict[str, Any]] = []
    try:
        found = page.find_tables()
        tables = list(getattr(found, "tables", []) or [])
    except Exception:
        return result

    total_cells = 0
    for table_index, table in enumerate(tables):
        rows_text = table.extract() or []
        row_objects = list(getattr(table, "rows", []) or [])
        row_count = int(getattr(table, "row_count", len(rows_text)) or len(rows_text))
        column_count = int(getattr(table, "col_count", 0) or 0)
        if row_count < 2 or column_count < 2:
            continue
        if total_cells + row_count * column_count > MAX_TABLE_CELLS:
            break
        total_cells += row_count * column_count
        all_rects = [rect for row in row_objects for rect in row.cells if rect]
        x_boundaries = _cluster_boundaries(value for rect in all_rects for value in (rect[0], rect[2]))
        y_boundaries = _cluster_boundaries(value for rect in all_rects for value in (rect[1], rect[3]))
        rows: List[Dict[str, Any]] = [{"row_index": index, "cells": []} for index in range(row_count)]
        covered = set()
        unresolved = []
        for source_row_index in range(row_count):
            source_cells = row_objects[source_row_index].cells if source_row_index < len(row_objects) else []
            text_cells = rows_text[source_row_index] if source_row_index < len(rows_text) else []
            for source_column_index, rect in enumerate(source_cells):
                if rect is None:
                    continue
                row_index = _nearest_boundary(y_boundaries, rect[1])
                row_end = _nearest_boundary(y_boundaries, rect[3])
                column_index = _nearest_boundary(x_boundaries, rect[0])
                column_end = _nearest_boundary(x_boundaries, rect[2])
                rowspan = max(1, row_end - row_index)
                colspan = max(1, column_end - column_index)
                value = text_cells[source_column_index] if source_column_index < len(text_cells) else ""
                value = "" if value is None else str(value).strip()
                cell = {
                    "cell_id": f"p{page.number + 1}_t{table_index}_r{row_index}_c{column_index}",
                    "row_index": row_index,
                    "column_index": column_index,
                    "rowspan": rowspan,
                    "colspan": colspan,
                    "text": value,
                    "source_text": value,
                    "bbox": _bbox_from_rect(rect, scale),
                    "source": "pdf_native_text",
                    "confidence": None,
                    "evidence": ["pdf_vector_geometry", "pdf_native_text"],
                    "unresolved": bool(re.search(r"[\ue000-\uf8ff]", value)),
                }
                if cell["unresolved"]:
                    unresolved.append({"row_index": row_index, "column_index": column_index,
                                       "reason": "private_use_glyph_requires_review"})
                if row_index < len(rows):
                    rows[row_index]["cells"].append(cell)
                for covered_row in range(row_index, min(row_count, row_index + rowspan)):
                    for covered_column in range(column_index, min(column_count, column_index + colspan)):
                        covered.add((covered_row, covered_column))
        for row_index in range(row_count):
            rows[row_index]["cells"].sort(key=lambda cell: cell["column_index"])
            for column_index in range(column_count):
                if (row_index, column_index) not in covered:
                    unresolved.append({"row_index": row_index, "column_index": column_index,
                                       "reason": "missing_geometry"})
        result.append({
            "block_id": f"p{page.number + 1}_table_{table_index}",
            "type": "table",
            "bbox": _bbox_from_rect(table.bbox, scale),
            "source": "pdf_vector_table",
            "confidence": None,
            "evidence": ["pdf_vector_geometry"],
            "header_rows": 1,
            "row_count": row_count,
            "column_count": column_count,
            "rows": rows,
            "unresolved": unresolved,
        })
    return result


def _point_in_bbox(x: float, y: float, bbox: Dict[str, Any]) -> bool:
    x0, y0, x1, y1 = _rect_from_bbox(bbox)
    return x0 <= x <= x1 and y0 <= y <= y1


def apply_ocr_to_tables(tables: List[Dict[str, Any]], lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map OCR words into geometry cells without changing unreadable/missing text."""
    tokens = []
    for line_index, line in enumerate(lines or []):
        words = line.get("words") or []
        if isinstance(line.get("bbox"), dict):
            x0, y0, x1, y1 = _rect_from_bbox(line["bbox"])
            confidences = [float(word["confidence"]) for word in words if word.get("confidence") is not None]
            tokens.append((line_index, 0, (x0 + x1) / 2, (y0 + y1) / 2,
                           str(line.get("text") or ""),
                           (sum(confidences) / len(confidences)) if confidences else None))
    for table in tables:
        for row in table.get("rows", []):
            for cell in row.get("cells", []):
                bbox = cell.get("bbox")
                if not isinstance(bbox, dict):
                    continue
                matches = [token for token in tokens if _point_in_bbox(token[2], token[3], bbox)]
                if not matches:
                    continue
                matches.sort(key=lambda token: (token[0], token[1]))
                grouped: Dict[int, List[str]] = {}
                for token in matches:
                    grouped.setdefault(token[0], []).append(token[4])
                value = "\n".join(" ".join(parts).strip() for parts in grouped.values()).strip()
                if value:
                    confidences = [float(token[5]) for token in matches if token[5] is not None]
                    cell["text"] = value
                    cell["source"] = "ocr"
                    cell["confidence"] = round(sum(confidences) / len(confidences), 4) if confidences else None
                    cell["evidence"] = ["pdf_vector_geometry", "ocr_word_bbox"]
        table["source"] = "pdf_vector_table+ocr"
        table["evidence"] = ["pdf_vector_geometry", "ocr_word_bbox"]
    return tables


def _line_clusters(values: List[int], max_gap: int = 4) -> List[int]:
    groups: List[List[int]] = []
    for value in values:
        if not groups or value - groups[-1][-1] > max_gap:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [round(sum(group) / len(group)) for group in groups]


def detect_image_table_grid(image: Any, lines: List[Dict[str, Any]], page_id: int) -> List[Dict[str, Any]]:
    """Conservative ruled-table detector for scanned/raster pages using pixel projections."""
    gray = image.convert("L")
    width, height = gray.size
    pixels = gray.load()
    horizontal = []
    vertical = []
    def longest_run(values: Iterable[bool], allowed_gap: int = 2) -> int:
        longest = current = gap = 0
        for dark in values:
            if dark:
                current += gap + 1
                gap = 0
                longest = max(longest, current)
            elif current and gap < allowed_gap:
                gap += 1
            else:
                current = gap = 0
        return longest
    for y in range(height):
        if longest_run((pixels[x, y] < 180 for x in range(width))) >= width * 0.18:
            horizontal.append(y)
    for x in range(width):
        if longest_run((pixels[x, y] < 180 for y in range(height))) >= height * 0.05:
            vertical.append(x)
    ys = _line_clusters(horizontal)
    xs = _line_clusters(vertical)
    if len(xs) < 3 or len(ys) < 3:
        return []
    # Keep the largest coherent grid. Lines must intersect most opposing axes.
    def intersection_ratio(axis_value: int, opposing: List[int], horizontal_axis: bool) -> float:
        hits = 0
        for other in opposing:
            x, y = (other, axis_value) if horizontal_axis else (axis_value, other)
            if any(pixels[min(width - 1, max(0, x + dx)), min(height - 1, max(0, y + dy))] < 180
                   for dx in range(-2, 3) for dy in range(-2, 3)):
                hits += 1
        return hits / max(1, len(opposing))
    ys = [y for y in ys if intersection_ratio(y, xs, True) >= 0.7]
    xs = [x for x in xs if intersection_ratio(x, ys, False) >= 0.7]
    if len(xs) < 3 or len(ys) < 3 or len(xs) * len(ys) > 20_001:
        return []
    rows = []
    for row_index in range(len(ys) - 1):
        cells = []
        for column_index in range(len(xs) - 1):
            cells.append({
                "cell_id": f"p{page_id}_image_t0_r{row_index}_c{column_index}",
                "row_index": row_index, "column_index": column_index,
                "rowspan": 1, "colspan": 1, "text": "", "source_text": "",
                "bbox": _bbox_from_rect((xs[column_index], ys[row_index], xs[column_index + 1], ys[row_index + 1])),
                "source": "ocr", "confidence": None,
                "evidence": ["image_line_geometry", "ocr_word_bbox"], "unresolved": False,
            })
        rows.append({"row_index": row_index, "cells": cells})
    table = {
        "block_id": f"p{page_id}_image_table_0", "type": "table",
        "bbox": _bbox_from_rect((xs[0], ys[0], xs[-1], ys[-1])),
        "source": "image_line_table+ocr", "confidence": None,
        "evidence": ["image_line_geometry", "ocr_word_bbox"], "header_rows": 1,
        "row_count": len(rows), "column_count": len(xs) - 1, "rows": rows, "unresolved": [],
    }
    return apply_ocr_to_tables([table], lines)


def build_page_layout(page_record: Dict[str, Any], tables: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    page_id = int(page_record.get("page_id", 1))
    tables = list(tables or [])
    table_rects = [_rect_from_bbox(table["bbox"]) for table in tables if isinstance(table.get("bbox"), dict)]
    source_blocks = [block for block in (page_record.get("blocks") or []) if not _inside_table(block, table_rects)]
    blocks = tables + _promote_tab_tables(page_id, _plain_blocks(page_id, source_blocks))
    blocks = blocks[:MAX_LAYOUT_BLOCKS]
    blocks.sort(key=lambda block: (_rect_from_bbox(block.get("bbox") or {})[1],
                                   _rect_from_bbox(block.get("bbox") or {})[0]))
    return {
        "layout_schema_version": LAYOUT_SCHEMA_VERSION,
        "page_id": page_id,
        "source_revision": hashlib.sha256(str(page_record.get("raw_text", "")).encode("utf-8")).hexdigest()[:16],
        "blocks": blocks,
        "unresolved_count": sum(len(block.get("unresolved", [])) for block in blocks),
    }


def ensure_document_layout(ocr_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a versioned layout document, including fallback for old OCR jobs."""
    pages = []
    for page in ocr_data.get("pages", []) if isinstance(ocr_data, dict) else []:
        layout = page.get("layout")
        if not isinstance(layout, dict) or layout.get("layout_schema_version") != LAYOUT_SCHEMA_VERSION:
            layout = build_page_layout(page)
        pages.append(layout)
    return {
        "layout_schema_version": LAYOUT_SCHEMA_VERSION,
        "job_id": str(ocr_data.get("job_id", "")),
        "ocr_schema_version": str(ocr_data.get("schema_version", "legacy")),
        "pages": pages,
    }


def compute_structured_source_revision(job_dir: str) -> str:
    digest = hashlib.sha256()
    for path in [os.path.join(job_dir, "ocr.json")]:
        if os.path.isfile(path):
            with open(path, "rb") as stream:
                digest.update(stream.read())
    for name in sorted(os.listdir(job_dir)) if os.path.isdir(job_dir) else []:
        if not name.startswith("page_"):
            continue
        for variant in ("raw.txt", "corrected.txt", "final.txt"):
            path = os.path.join(job_dir, name, variant)
            digest.update(f"{name}/{variant}\0".encode("utf-8"))
            if os.path.isfile(path):
                with open(path, "rb") as stream:
                    digest.update(stream.read())
    return digest.hexdigest()[:16]


def _attach_text_variants(document: Dict[str, Any], job_dir: str) -> None:
    for page in document.get("pages", []):
        page_id = int(page.get("page_id", 1))
        page_dir = os.path.join(job_dir, f"page_{page_id:02d}")
        variants = {}
        for variant in ("raw", "corrected", "final"):
            path = os.path.join(page_dir, f"{variant}.txt")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as stream:
                    variants[variant] = stream.read()
        page["text_variants"] = variants
        page["has_manual_or_corrected_text"] = bool(
            variants.get("final", variants.get("raw", "")) != variants.get("raw", "")
            or variants.get("corrected", variants.get("raw", "")) != variants.get("raw", "")
        )


def render_structured_text(document: Dict[str, Any]) -> str:
    output: List[str] = []
    for page in document.get("pages", []):
        output.append(f"--- Page {page.get('page_id', 1)} ---")
        for block in page.get("blocks", []):
            block_type = block.get("type")
            if block_type == "table":
                for row in block.get("rows", []):
                    inferred_columns = max(
                        (int(cell.get("column_index", index)) + int(cell.get("colspan", 1))
                         for index, cell in enumerate(row.get("cells", []))),
                        default=1,
                    )
                    column_count = max(inferred_columns, int(block.get("column_count", 0) or 0))
                    values = [""] * column_count
                    for fallback_index, cell in enumerate(row.get("cells", [])):
                        column_index = int(cell.get("column_index", fallback_index))
                        if 0 <= column_index < column_count:
                            values[column_index] = str(cell.get("text", ""))
                    output.append("\t".join(values))
            elif block_type == "list":
                for item in block.get("items", []):
                    output.append(f"{item.get('marker', '-')} {item.get('text', '')}")
            else:
                output.append(str(block.get("text", "")))
        output.append("")
    # Strip only document separator newlines. Tabs encode empty trailing cells.
    return "\n".join(output).rstrip("\n") + "\n"


def render_structured_html(document: Dict[str, Any], title: str = "Structured OCR") -> str:
    sections: List[str] = []
    for page in document.get("pages", []):
        body: List[str] = []
        for block in page.get("blocks", []):
            block_id = html.escape(str(block.get("block_id", "")), quote=True)
            bbox = html.escape(json.dumps(block.get("bbox"), ensure_ascii=False, separators=(",", ":")), quote=True)
            attrs = f' data-block-id="{block_id}" data-bbox="{bbox}"'
            block_type = block.get("type")
            if block_type == "table":
                rows = []
                for row_index, row in enumerate(block.get("rows", [])):
                    cells = []
                    for cell in row.get("cells", []):
                        tag = "th" if row_index < int(block.get("header_rows", 0)) else "td"
                        span = ""
                        rowspan, colspan = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
                        if rowspan > 1:
                            span += f' rowspan="{rowspan}"'
                        if colspan > 1:
                            span += f' colspan="{colspan}"'
                        cell_bbox = html.escape(json.dumps(cell.get("bbox"), ensure_ascii=False, separators=(",", ":")), quote=True)
                        cell_id = html.escape(str(cell.get("cell_id", "")), quote=True)
                        cells.append(f'<{tag}{span} data-cell-id="{cell_id}" data-bbox="{cell_bbox}">{html.escape(str(cell.get("text", "")))}</{tag}>')
                    rows.append("<tr>" + "".join(cells) + "</tr>")
                head_count = int(block.get("header_rows", 0))
                head = "<thead>" + "".join(rows[:head_count]) + "</thead>" if head_count else ""
                body_rows = "<tbody>" + "".join(rows[head_count:]) + "</tbody>"
                body.append(f"<table{attrs}>{head}{body_rows}</table>")
            elif block_type == "list":
                tag = "ol" if block.get("list_type") == "ordered" else "ul"
                items = "".join(f"<li>{html.escape(str(item.get('text', '')))}</li>" for item in block.get("items", []))
                body.append(f"<{tag}{attrs}>{items}</{tag}>")
            else:
                tag = block_type if block_type in {"h1", "h2", "h3"} else "p"
                body.append(f"<{tag}{attrs}>{html.escape(str(block.get('text', '')))}</{tag}>")
        page_id = int(page.get("page_id", 1))
        sections.append(f'<section data-page="{page_id}" id="page-{page_id}">' + "".join(body) + "</section>")
    safe_title = html.escape(title)
    return ("<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            f"<title>{safe_title}</title><style>body{{font-family:system-ui,sans-serif;margin:2rem}}section{{margin-bottom:2rem}}"
            "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #999;padding:.4rem;vertical-align:top}"
            "th{background:#eee}p{white-space:pre-wrap}</style></head><body><main>" + "".join(sections) + "</main></body></html>")


def generate_structured_exports(job_id: str, files_dir: str = "files") -> Dict[str, Any]:
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    ocr_path = os.path.join(job_dir, "ocr.json")
    if not os.path.isfile(ocr_path):
        raise FileNotFoundError("OCR artifact not found")
    with open(ocr_path, "r", encoding="utf-8") as stream:
        ocr_data = json.load(stream)
    document = ensure_document_layout(ocr_data)
    _attach_text_variants(document, job_dir)
    source_revision = compute_structured_source_revision(job_dir)
    document["source_revision"] = source_revision
    text_content = render_structured_text(document)
    html_content = render_structured_html(document, title=f"Document {job_id}")
    export_dir = os.path.join(job_dir, "export", "structured")
    os.makedirs(export_dir, exist_ok=True)
    atomic_write_json(os.path.join(export_dir, "layout.json"), document)
    atomic_write_text(os.path.join(export_dir, "structured.txt"), text_content)
    atomic_write_text(os.path.join(export_dir, "structured.html"), html_content)
    revision = hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    meta = {"layout_schema_version": LAYOUT_SCHEMA_VERSION, "layout_revision": revision,
            "source_revision": source_revision,
            "pages": len(document["pages"]), "unresolved_count": sum(p.get("unresolved_count", 0) for p in document["pages"])}
    atomic_write_json(os.path.join(export_dir, "meta.json"), meta)
    return meta


def get_structured_status(job_id: str, files_dir: str = "files") -> Dict[str, Any]:
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    meta_path = os.path.join(job_dir, "export", "structured", "meta.json")
    if not os.path.isfile(meta_path):
        return {"status": "not_generated", "is_stale": False}
    with open(meta_path, "r", encoding="utf-8") as stream:
        meta = json.load(stream)
    current_revision = compute_structured_source_revision(job_dir)
    is_stale = meta.get("source_revision") != current_revision
    return {"status": "stale" if is_stale else "ready", "is_stale": is_stale,
            "current_source_revision": current_revision, **meta}
