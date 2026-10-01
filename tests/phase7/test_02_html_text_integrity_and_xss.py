"""
Phase 7 Test 2: HTML Text Integrity, 100% Preservation, and XSS Sanitization.
"""
import os
import re
import html
import shutil
import tempfile
import unittest
from src.html_exporter import generate_basic_html, sanitize_text


class TestHtmlTextIntegrityAndXSS(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.job_id = "job_test_integrity_xss"
        self.job_dir = os.path.join(self.tmp_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_adversarial_xss_characters_escaped(self):
        """Adversarial patterns like <script>, &, quotes, <!--, ]]>, and controls are safe."""
        adversarial_input = "<script>alert('xss')</script> & <b>test</b> 'quoted' \"double\" <!-- comment --> ]]> \x00\x08"
        p_dir = os.path.join(self.job_dir, "page_01")
        os.makedirs(p_dir, exist_ok=True)

        with open(os.path.join(p_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write(adversarial_input)

        html_out, _ = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        # Must not contain raw executable tags
        self.assertNotIn("<script>", html_out)
        self.assertNotIn("alert('xss')", html_out)
        self.assertNotIn("<!-- comment -->", html_out)
        self.assertNotIn("\x00", html_out)
        self.assertNotIn("\x08", html_out)

        # Must contain escaped representations
        self.assertIn("&lt;script&gt;", html_out)
        self.assertIn("&amp;", html_out)
        self.assertIn("Content-Security-Policy", html_out)

    def test_02_text_100_percent_content_equality(self):
        """Every character in final.txt of completed pages must be represented in HTML in original sequence."""
        thai_text_lines = [
            "บทที่ 1 บทนำและหลักการ",
            "การเรียนการสอนในยุคปัจจุบันมีความก้าวหน้าทางเทคโนโลยีอย่างมาก",
            "ตารางข้อมูล\t100\t200\t300",
            "ข้อความสำคัญเพิ่มเติม",
        ]
        full_text = "\n".join(thai_text_lines)

        p_dir = os.path.join(self.job_dir, "page_01")
        os.makedirs(p_dir, exist_ok=True)
        with open(os.path.join(p_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write(full_text)

        html_out, _ = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        # Strip all HTML tags from output and unescape HTML entities
        stripped_text = re.sub(r"<[^>]+>", "", html_out)
        unescaped_text = html.unescape(stripped_text)

        for line in thai_text_lines:
            self.assertIn(line.strip(), unescaped_text)

        # Tab line must have pre-wrap
        self.assertIn('class="pre-wrap"', html_out)

    def test_03_failed_and_cancelled_page_markers(self):
        """Failed or cancelled pages include clear marker without silent data loss."""
        # Page 1: OK
        p1_dir = os.path.join(self.job_dir, "page_01")
        os.makedirs(p1_dir, exist_ok=True)
        with open(os.path.join(p1_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("หน้าหนึ่งสำเร็จสมบูรณ์")

        # Page 2: Cancelled
        p2_dir = os.path.join(self.job_dir, "page_02")
        os.makedirs(p2_dir, exist_ok=True)
        with open(os.path.join(p2_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("[PAGE 2: CANCELLED]")

        html_out, _ = generate_basic_html(self.job_id, files_dir=self.tmp_dir)

        self.assertIn("หน้าหนึ่งสำเร็จสมบูรณ์", html_out)
        self.assertIn('class="page-container page-failed"', html_out)
        self.assertIn("[PAGE 2: CANCELLED]", html_out)


if __name__ == "__main__":
    unittest.main()
