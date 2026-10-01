"""
Phase 7 Test 3: Heading Hierarchy, Typography Rules, and Scanned Page Rules.
"""
import os
import re
import json
import shutil
import tempfile
import unittest
from src.html_exporter import generate_basic_html, determine_line_heading


class TestHeadingAndTypography(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.job_id = "job_test_typography"
        self.job_dir = os.path.join(self.tmp_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_single_h1_and_hierarchy_ordering(self):
        """Document has at most one h1, and heading levels do not jump."""
        p1_dir = os.path.join(self.job_dir, "page_01")
        p2_dir = os.path.join(self.job_dir, "page_02")
        os.makedirs(p1_dir, exist_ok=True)
        os.makedirs(p2_dir, exist_ok=True)

        # Page 1: Chapter 1 (h1 candidate) and Section 1.1 (h2 candidate)
        p1_text = "บทที่ 1 บทนำ\n1.1 วัตถุประสงค์\nเนื้อหาบทนำทั่วไป"
        with open(os.path.join(p1_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write(p1_text)

        # Page 2: Chapter 2 (must become h2 because h1 already used on page 1)
        p2_text = "บทที่ 2 ทฤษฎีและงานวิจัยที่เกี่ยวข้อง\n2.1 ทฤษฎีพื้นฐาน\nเนื้อหารายละเอียด"
        with open(os.path.join(p2_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write(p2_text)

        # Mock ocr.json with digital typography styles
        ocr_doc = {
            "job_id": self.job_id,
            "pages": [
                {
                    "page_id": 1,
                    "blocks": [
                        {
                            "block_id": "p1_b0",
                            "lines": [
                                {
                                    "text": "บทที่ 1 บทนำ",
                                    "style": {"size_median": 20.0, "size_max": 20.0, "bold_ratio": 1.0, "evidence": "pdf_span_flags"},
                                },
                                {
                                    "text": "1.1 วัตถุประสงค์",
                                    "style": {"size_median": 16.0, "size_max": 16.0, "bold_ratio": 1.0, "evidence": "pdf_span_flags"},
                                },
                                {
                                    "text": "เนื้อหาบทนำทั่วไป",
                                    "style": {"size_median": 14.0, "size_max": 14.0, "bold_ratio": 0.0, "evidence": "pdf_span_flags"},
                                },
                            ],
                        }
                    ],
                },
                {
                    "page_id": 2,
                    "blocks": [
                        {
                            "block_id": "p2_b0",
                            "lines": [
                                {
                                    "text": "บทที่ 2 ทฤษฎีและงานวิจัยที่เกี่ยวข้อง",
                                    "style": {"size_median": 20.0, "size_max": 20.0, "bold_ratio": 1.0, "evidence": "pdf_span_flags"},
                                },
                                {
                                    "text": "2.1 ทฤษฎีพื้นฐาน",
                                    "style": {"size_median": 16.0, "size_max": 16.0, "bold_ratio": 1.0, "evidence": "pdf_span_flags"},
                                },
                                {
                                    "text": "เนื้อหารายละเอียด",
                                    "style": {"size_median": 14.0, "size_max": 14.0, "bold_ratio": 0.0, "evidence": "pdf_span_flags"},
                                },
                            ],
                        }
                    ],
                },
            ],
        }
        with open(os.path.join(self.job_dir, "ocr.json"), "w", encoding="utf-8") as f:
            json.dump(ocr_doc, f, ensure_ascii=False)

        html_out, _ = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        # Count <h1> tags
        h1_matches = re.findall(r"<h1\b[^>]*>", html_out)
        self.assertEqual(len(h1_matches), 1, "Exactly one h1 allowed across document")
        self.assertIn('<h1 data-src="p1_b0">', html_out)

        # Page 2 Chapter 2 must be h2 (not h1)
        self.assertIn('<h2 data-src="p2_b0">', html_out)

    def test_02_scanned_documents_never_guess_bold_or_italic(self):
        """Scanned document with evidence='none' must not produce <b> or <i> tags."""
        p1_dir = os.path.join(self.job_dir, "page_01")
        os.makedirs(p1_dir, exist_ok=True)
        with open(os.path.join(p1_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("ข้อความจากเอกสารสแกนลายน้ำชัดเจน")

        # Mock ocr.json without style (OneOCR output)
        ocr_doc = {
            "job_id": self.job_id,
            "pages": [
                {
                    "page_id": 1,
                    "blocks": [
                        {
                            "block_id": "p1_b0",
                            "lines": [
                                {
                                    "text": "ข้อความจากเอกสารสแกนลายน้ำชัดเจน",
                                    "style": {"size_median": 0.0, "size_max": 0.0, "bold_ratio": 0.0, "italic_ratio": 0.0, "evidence": "none"},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with open(os.path.join(self.job_dir, "ocr.json"), "w", encoding="utf-8") as f:
            json.dump(ocr_doc, f, ensure_ascii=False)

        html_out, _ = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        self.assertNotIn("<b>", html_out)
        self.assertNotIn("<i>", html_out)
        self.assertIn("<p data-src=\"p1_b0\">ข้อความจากเอกสารสแกนลายน้ำชัดเจน</p>", html_out)


if __name__ == "__main__":
    unittest.main()
