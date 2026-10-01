"""
Phase 7 Test 4: AI Semantic HTML Export and Strict Annotation Validator.
"""
import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from src.html_exporter import (
    AIAnnotationValidator,
    generate_basic_html,
    generate_ai_html,
    get_export_status,
)


class TestAiHtmlAndValidator(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.job_id = "job_test_ai_validator"
        self.job_dir = os.path.join(self.tmp_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)

        p1_dir = os.path.join(self.job_dir, "page_01")
        os.makedirs(p1_dir, exist_ok=True)
        with open(os.path.join(p1_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("หัวข้อหลักของเอกสาร\nย่อหน้าเนื้อหาทั่วไปที่ 1\nย่อหน้าเนื้อหาทั่วไปที่ 2\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_validator_rejection_criteria(self):
        """Validator rejects invalid structures, unauthorized tags, multiple h1, duplicate units."""
        validator = AIAnnotationValidator(["u0", "u1", "u2"])

        # 1. Multiple h1
        ok, reason, _ = validator.validate([{"unit": "u0", "tag": "h1"}, {"unit": "u1", "tag": "h1"}])
        self.assertFalse(ok)
        self.assertIn("Multiple h1", reason)

        # 2. Prohibited tag
        ok, reason, _ = validator.validate([{"unit": "u0", "tag": "script"}])
        self.assertFalse(ok)
        self.assertIn("Prohibited tag", reason)

        # 3. Unknown unit
        ok, reason, _ = validator.validate([{"unit": "u999", "tag": "p"}])
        self.assertFalse(ok)
        self.assertIn("unknown unit", reason)

        # 4. Duplicate unit
        ok, reason, _ = validator.validate([{"unit": "u0", "tag": "p"}, {"unit": "u0", "tag": "h2"}])
        self.assertFalse(ok)
        self.assertIn("Duplicate unit", reason)

        # 5. Hierarchy jump (h1 -> h3)
        ok, reason, _ = validator.validate([{"unit": "u0", "tag": "h1"}, {"unit": "u1", "tag": "h3"}])
        self.assertFalse(ok)
        self.assertIn("jumped", reason)

    def test_02_ai_offline_fallback_preserves_basic(self):
        """When AI is offline (llm_client is None), basic.html is preserved and meta reflects offline."""
        html_out, meta = generate_ai_html(self.job_id, files_dir=self.tmp_dir, llm_client=None)

        self.assertEqual(meta.get("validator_status"), "locked_ai_offline")
        export_dir = os.path.join(self.job_dir, "export")
        self.assertTrue(os.path.exists(os.path.join(export_dir, "basic.html")))
        # ai.html should NOT be published on offline
        self.assertFalse(os.path.exists(os.path.join(export_dir, "ai.html")))

    def test_03_ai_successful_annotation_and_malformed_fallback(self):
        """Valid annotations apply data-src='...,ai', while malformed AI response falls back to basic."""
        # 1. Malformed AI response
        mock_client_bad = MagicMock()
        mock_client_bad.generate.return_value = "Sorry, I am an AI and cannot process this request."

        html_bad, meta_bad = generate_ai_html(self.job_id, files_dir=self.tmp_dir, llm_client=mock_client_bad)
        self.assertEqual(meta_bad.get("validator_status"), "error")

        # 2. Valid AI response
        mock_client_good = MagicMock()
        mock_client_good.generate.return_value = json.dumps([
            {"unit": "u0", "tag": "h1"},
            {"unit": "u1", "tag": "p"},
            {"unit": "u2", "tag": "p"},
        ])

        html_good, meta_good = generate_ai_html(self.job_id, files_dir=self.tmp_dir, llm_client=mock_client_good)
        self.assertEqual(meta_good.get("validator_status"), "passed")
        self.assertIn("ai", html_good)
        export_dir = os.path.join(self.job_dir, "export")
        self.assertTrue(os.path.exists(os.path.join(export_dir, "ai.html")))


if __name__ == "__main__":
    unittest.main()
