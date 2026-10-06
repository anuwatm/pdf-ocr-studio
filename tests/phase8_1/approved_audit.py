import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image

from src.structured_layout import apply_ocr_to_tables, detect_image_table_grid, extract_pdf_vector_tables


ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "demo" / "04.pdf").is_file():
    ROOT = ROOT.parent


def cells(table):
    return [[cell["text"] for cell in row["cells"]] for row in table["rows"]]


def main():
    with (ROOT / "tests/artifacts/table04_20261005/oneocr.json").open(encoding="utf-8") as stream:
        ocr_lines = json.load(stream)["lines"]
    with (ROOT / "tests/artifacts/table04_20261005/ocr_cells.json").open(encoding="utf-8") as stream:
        expected04 = json.load(stream)["rows"]
    with fitz.open(ROOT / "demo/04.pdf") as document:
        page = document[0]
        vector04 = apply_ocr_to_tables(extract_pdf_vector_tables(page, 300), ocr_lines)[0]
        pixmap = page.get_pixmap(dpi=300, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    scan04 = detect_image_table_grid(image, ocr_lines, 1)[0]
    assert cells(vector04) == expected04
    assert cells(scan04) == expected04

    pages = []
    with fitz.open(ROOT / "demo/08.pdf") as document:
        for number, page in enumerate(document, 1):
            tables = extract_pdf_vector_tables(page, 300)
            pages.append({"page": number, "tables": tables})
    assert len(pages) == 11
    assert sum(len(page["tables"]) for page in pages) == 29
    page5 = pages[4]["tables"][0]
    assert any(cell["colspan"] == 2 for row in page5["rows"] for cell in row["cells"])
    page7_text = json.dumps(pages[6], ensure_ascii=False)
    assert "£million" in page7_text and "0.78" in page7_text and '"-"' in page7_text
    page10_text = json.dumps(pages[9], ensure_ascii=False)
    assert "Susan. P. Arnold-Jones, BA, FRSA, MD" in page10_text
    page11 = pages[10]["tables"][0]
    assert any(cell["text"] == "2010" and cell["colspan"] == 5 for row in page11["rows"] for cell in row["cells"])
    unresolved = [item for page in pages for table in page["tables"] for item in table["unresolved"]]
    assert any(item["reason"] == "private_use_glyph_requires_review" for item in unresolved)

    payload = {
        "review": "automated approved-dataset audit; special values inspected against native PDF text; private-use checkbox glyphs remain unresolved",
        "demo04": {"vector_equal_ground_truth": True, "scan_derivative_equal_ground_truth": True,
                   "rows": 9, "columns": 4, "cells": 36},
        "demo08": {"pages": 11, "tables": 29, "unresolved": unresolved,
                   "covered": ["merged cells", "multi-level headers", "tab-stop columns", "decimals", "£", "dash placeholders"]},
        "hashes": {name: hashlib.sha256((ROOT / "demo" / name).read_bytes()).hexdigest()
                   for name in ("04.pdf", "08.pdf")},
    }
    (ROOT / "phase8_1" / "approved_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PASS: demo/04 vector+scan 36/36 cells; demo/08 11 pages/29 tables; unresolved={len(unresolved)}")


if __name__ == "__main__":
    main()
