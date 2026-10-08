import json
import os
import unittest
import uuid

import fitz
from PIL import Image
from fastapi.testclient import TestClient

from src.database import JobDatabase
from src.server import app
from src.structured_layout import (
    LAYOUT_SCHEMA_VERSION,
    build_page_layout,
    apply_ocr_to_tables,
    detect_image_table_grid,
    ensure_document_layout,
    extract_pdf_vector_tables,
    generate_structured_exports,
    render_structured_html,
    render_structured_text,
)
from src.epub_exporter import build_epub, prepare_epub_preview, validate_epub_bytes
from src.html_exporter import generate_ai_html, sanitize_final_html


RUNTIME = os.path.abspath("tests/artifacts/phase8_1_runtime")
DEMO_DIR = "demo" if os.path.isdir("demo") else os.path.abspath(os.path.join("..", "demo"))


class TestStructuredLayout(unittest.TestCase):
    def test_legacy_fallback_and_list_do_not_treat_table_numbers_as_list(self):
        page = {
            "page_id": 1,
            "raw_text": "01\tTeacher\n1. First item\n- Bullet",
            "blocks": [{
                "block_id": "p1_b1", "source": "ocr", "confidence": 0.9,
                "bbox": {"x1": 0, "y1": 0, "x2": 100, "y2": 0, "x3": 100, "y3": 60, "x4": 0, "y4": 60},
                "lines": [
                    {"text": "01\tTeacher", "bbox": None},
                    {"text": "1. First item", "bbox": None},
                    {"text": "- Bullet", "bbox": None},
                ],
            }],
        }
        layout = build_page_layout(page)
        self.assertEqual(layout["layout_schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(layout["blocks"][0]["type"], "paragraph")
        self.assertEqual(layout["blocks"][1]["type"], "list")
        self.assertEqual(layout["blocks"][2]["type"], "list")

        old_job = {"job_id": "old", "schema_version": "2.0.0", "pages": [page]}
        document = ensure_document_layout(old_job)
        self.assertEqual(document["ocr_schema_version"], "2.0.0")
        self.assertEqual(len(document["pages"]), 1)

    def test_consecutive_tab_rows_preserve_empty_cells(self):
        page = {"page_id": 1, "raw_text": "A\tB\tC\n1\t\t3", "blocks": [
            {"block_id": "r1", "text": "A\tB\tC", "source": "ocr"},
            {"block_id": "r2", "text": "1\t\t3", "source": "ocr"},
        ]}
        layout = build_page_layout(page)
        table = layout["blocks"][0]
        self.assertEqual(table["type"], "table")
        self.assertEqual((table["row_count"], table["column_count"]), (2, 3))
        self.assertEqual(table["rows"][1]["cells"][1]["text"], "")
        self.assertGreater(layout["unresolved_count"], 0)

    def test_heading_uses_style_evidence_and_keeps_hierarchy(self):
        page = {"page_id": 1, "raw_text": "Title\nBody", "blocks": [{
            "block_id": "b1", "source": "pdf_text", "lines": [
                {"text": "Title", "style": {"size_median": 20, "bold_ratio": 1}},
                {"text": "Body", "style": {"size_median": 12, "bold_ratio": 0}},
            ]}]}
        blocks = build_page_layout(page)["blocks"]
        self.assertEqual([block["type"] for block in blocks], ["h1", "paragraph"])
        self.assertIn("font_size", blocks[0]["evidence"])

    def test_demo04_vector_table_structure(self):
        with fitz.open(os.path.join(DEMO_DIR, "04.pdf")) as document:
            tables = extract_pdf_vector_tables(document[0], dpi=300)
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual((table["row_count"], table["column_count"]), (9, 4))
        self.assertEqual(sum(len(row["cells"]) for row in table["rows"]), 36)
        self.assertEqual([row["cells"][0]["text"] for row in table["rows"][1:]],
                         ["01", "02", "03", "04", "05", "06", "07", "08"])
        self.assertTrue(all(cell["bbox"] for row in table["rows"] for cell in row["cells"]))

    def test_demo08_page5_merged_cells_have_colspan(self):
        with fitz.open(os.path.join(DEMO_DIR, "08.pdf")) as document:
            table = extract_pdf_vector_tables(document[4], dpi=300)[0]
        spans = [cell["colspan"] for row in table["rows"] for cell in row["cells"]]
        self.assertIn(2, spans)
        self.assertEqual(table["unresolved"], [])

    def test_demo04_ocr_words_map_to_vector_and_scanned_grid(self):
        fixture = os.path.abspath("tests/artifacts/table04_20261005/oneocr.json")
        if not os.path.isfile(fixture):
            fixture = os.path.abspath(os.path.join("..", "tests/artifacts/table04_20261005/oneocr.json"))
        with open(fixture, encoding="utf-8") as stream:
            lines = json.load(stream)["lines"]
        with fitz.open(os.path.join(DEMO_DIR, "04.pdf")) as document:
            page = document[0]
            vector = apply_ocr_to_tables(extract_pdf_vector_tables(page, dpi=300), lines)[0]
            pixmap = page.get_pixmap(dpi=300, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        scanned = detect_image_table_grid(image, lines, 1)[0]
        for table in (vector, scanned):
            self.assertEqual((table["row_count"], table["column_count"]), (9, 4))
            values = [[cell["text"] for cell in row["cells"]] for row in table["rows"]]
            self.assertEqual([row[0] for row in values[1:]], ["01", "02", "03", "04", "05", "06", "07", "08"])
            self.assertEqual(sum(bool(value) for row in values for value in row), 36)
            self.assertEqual(values[4][1], "นางสาวจิดาภา เขื่อนแก้ว")
            self.assertEqual(values[4][2], "เกมยุบยิบทายใจ")

    def test_text_html_preserve_empty_cells_and_escape_content(self):
        table = {
            "block_id": "p1_t0", "type": "table", "bbox": None, "header_rows": 1,
            "rows": [
                {"row_index": 0, "cells": [
                    {"cell_id": "h1", "text": "A", "rowspan": 1, "colspan": 1, "bbox": None},
                    {"cell_id": "h2", "text": "B", "rowspan": 1, "colspan": 1, "bbox": None}]},
                {"row_index": 1, "cells": [
                    {"cell_id": "c1", "text": "<unsafe>", "rowspan": 1, "colspan": 1, "bbox": None},
                    {"cell_id": "c2", "text": "", "rowspan": 1, "colspan": 1, "bbox": None}]},
            ],
        }
        doc = {"pages": [{"page_id": 1, "blocks": [table]}]}
        text = render_structured_text(doc)
        markup = render_structured_html(doc)
        self.assertIn("<unsafe>\t\n", text)
        self.assertIn("&lt;unsafe&gt;", markup)
        self.assertNotIn("<unsafe>", markup)
        self.assertIn("<thead>", markup)
        self.assertIn("<tbody>", markup)

    def test_html_sanitizer_and_ai_preserve_table_model(self):
        sanitized = sanitize_final_html('<table data-block-id="t1" data-bbox="{&quot;x1&quot;:1}"><tbody><tr><td data-cell-id="c1" colspan="2" onclick="bad()">A</td></tr></tbody></table>')
        self.assertIn('<table data-block-id="t1" data-bbox="{&quot;x1&quot;:1}">', sanitized)
        self.assertIn('<td data-cell-id="c1" colspan="2">A</td>', sanitized)
        self.assertNotIn("onclick", sanitized)
        job_id = "ai_table_" + uuid.uuid4().hex[:8]
        export = os.path.join(RUNTIME, job_id, "export")
        os.makedirs(export, exist_ok=True)
        source = '<html><body><table><tbody><tr><td>A</td><td>B</td></tr></tbody></table><p>Body</p></body></html>'
        with open(os.path.join(export, "basic.html"), "w", encoding="utf-8") as stream:
            stream.write(source)
        class Client:
            model = "fixture"
            def generate(self, **kwargs):
                return '[{"unit":"u0","tag":"p"}]'
        result, meta = generate_ai_html(job_id, files_dir=RUNTIME, llm_client=Client())
        self.assertEqual(meta["validator_status"], "passed")
        self.assertIn("<table>", result)
        self.assertIn("<td>A</td><td>B</td>", result)


class TestStructuredEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(RUNTIME, exist_ok=True)
        cls.database = JobDatabase(os.path.join(RUNTIME, "jobs.db"))

    def test_generate_and_download_without_ocr_or_ai(self):
        from unittest.mock import patch
        job_id = "structured_" + uuid.uuid4().hex[:10]
        self.database.create_job(job_id, "table.pdf", os.path.join(RUNTIME, "table.pdf"), 100, 1, False)
        job_dir = os.path.join(RUNTIME, job_id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "ocr.json"), "w", encoding="utf-8") as stream:
            json.dump({"schema_version": "2.0.0", "job_id": job_id, "pages": [{
                "page_id": 1, "raw_text": "ข้อความ", "blocks": [{"block_id": "p1_b1", "text": "ข้อความ", "source": "ocr"}]
            }]}, stream, ensure_ascii=False)

        with patch("src.server.DEFAULT_OUTPUT_DIR", RUNTIME), patch("src.server.db", self.database):
            client = TestClient(app)
            response = client.post(f"/api/jobs/{job_id}/export/structured")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["meta"]["layout_schema_version"], LAYOUT_SCHEMA_VERSION)
            for variant in ("text", "html", "layout"):
                download = client.get(f"/api/jobs/{job_id}/export/structured/{variant}")
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.headers["x-content-type-options"], "nosniff")
            status = client.get(f"/api/jobs/{job_id}/export/structured/status")
            self.assertEqual(status.json()["status"], "ready")

            page_dir = os.path.join(job_dir, "page_01")
            os.makedirs(page_dir, exist_ok=True)
            with open(os.path.join(page_dir, "final.txt"), "w", encoding="utf-8") as stream:
                stream.write("แก้ไขแล้ว")
            stale = client.get(f"/api/jobs/{job_id}/export/structured/status")
            self.assertEqual(stale.json()["status"], "stale")
            self.assertTrue(stale.json()["is_stale"])

    def test_structured_table_survives_epub(self):
        job_id = "structured_epub_" + uuid.uuid4().hex[:10]
        job_dir = os.path.join(RUNTIME, job_id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "ocr.json"), "w", encoding="utf-8") as stream:
            json.dump({"schema_version": "2.0.0", "job_id": job_id, "pages": [{
                "page_id": 1, "raw_text": "A\tB\n1\t2", "blocks": [
                    {"block_id": "r1", "text": "A\tB", "source": "ocr"},
                    {"block_id": "r2", "text": "1\t2", "source": "ocr"},
                ]}]}, stream)
        generate_structured_exports(job_id, files_dir=RUNTIME)
        preview = prepare_epub_preview(job_id, source_variant="structured", files_dir=RUNTIME,
                                       chapter_split="page")
        result = build_epub(job_id, preview["preview_revision"], files_dir=RUNTIME)
        self.assertTrue(result["validation"]["valid"])
        import zipfile
        with zipfile.ZipFile(os.path.join(job_dir, "export", "epub", "book.epub")) as package:
            chapter = package.read("EPUB/text/chapter-001.xhtml").decode("utf-8")
        self.assertIn("<table", chapter)
        self.assertIn("<td", chapter)
        with open(os.path.join(job_dir, "export", "epub", "book.epub"), "rb") as stream:
            self.assertTrue(validate_epub_bytes(stream.read())["valid"])

        preview = prepare_epub_preview(job_id, source_variant="structured", files_dir=RUNTIME,
                                       chapter_split="page")
        page_dir = os.path.join(job_dir, "page_01")
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "final.txt"), "w", encoding="utf-8") as stream:
            stream.write("changed after structured preview")
        with self.assertRaisesRegex(ValueError, "structured export is stale"):
            build_epub(job_id, preview["preview_revision"], files_dir=RUNTIME)


if __name__ == "__main__":
    unittest.main()
