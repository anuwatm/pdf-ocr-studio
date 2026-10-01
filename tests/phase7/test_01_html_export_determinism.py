"""
Phase 7 Test 1: HTML Export Determinism and Byte-Identical Repeatability.
"""
import os
import json
import shutil
import tempfile
import unittest
from src.html_exporter import generate_basic_html, get_export_status, compute_source_revision


class TestHtmlExportDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.job_id = "job_test_determinism"
        self.job_dir = os.path.join(self.tmp_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)

        # Create 2 mock pages
        for p_num in (1, 2):
            p_dir = os.path.join(self.job_dir, f"page_{p_num:02d}")
            os.makedirs(p_dir, exist_ok=True)
            text = f"บทที่ {p_num} การทดสอบระบบ\nนี่คือเนื้อหาย่อหน้าที่หนึ่งสำหรับหน้า {p_num}\nย่อหน้าที่สองมีความสำคัญมาก\n"
            with open(os.path.join(p_dir, "raw.txt"), "w", encoding="utf-8") as f:
                f.write(text)
            with open(os.path.join(p_dir, "final.txt"), "w", encoding="utf-8") as f:
                f.write(text)

        # Document level final.txt
        with open(os.path.join(self.job_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("บทที่ 1 การทดสอบระบบ\n\f\nบทที่ 2 การทดสอบระบบ\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_byte_identical_determinism(self):
        """Repeated generation of basic.html from identical inputs yields byte-identical hash."""
        html1, meta1 = generate_basic_html(self.job_id, files_dir=self.tmp_dir)
        html2, meta2 = generate_basic_html(self.job_id, files_dir=self.tmp_dir)
        html3, meta3 = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        self.assertEqual(meta1["hash"], meta2["hash"])
        self.assertEqual(meta2["hash"], meta3["hash"])
        self.assertEqual(html1, html2)
        self.assertEqual(html2, html3)
        self.assertTrue(html1.startswith("<!doctype html>"))
        self.assertIn('<html lang="th">', html1)
        self.assertIn('<meta charset="utf-8">', html1)

    def test_02_source_revision_tracking(self):
        """source_revision changes when final.txt is updated, and status reports stale."""
        _, meta1 = generate_basic_html(self.job_id, files_dir=self.tmp_dir)
        initial_rev = meta1["source_revision"]
        self.assertNotEqual(initial_rev, "empty")

        status_before = get_export_status(self.job_id, files_dir=self.tmp_dir)
        self.assertFalse(status_before["is_stale"])
        self.assertTrue(status_before["has_basic"])

        # Edit page 1 final.txt
        p1_final = os.path.join(self.job_dir, "final.txt")
        with open(p1_final, "w", encoding="utf-8") as f:
            f.write("ข้อความแก้ไขใหม่โดยผู้ใช้")

        status_after = get_export_status(self.job_id, files_dir=self.tmp_dir)
        self.assertTrue(status_after["is_stale"])
        self.assertNotEqual(status_after["source_revision"], initial_rev)


if __name__ == "__main__":
    unittest.main()
