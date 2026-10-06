"""Phase 8 API tests using a retained workspace (no test artifact deletion)."""

import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.database import JobDatabase
from src.server import app


API_ROOT = os.path.abspath("tests/artifacts/phase8_api_runtime")


class TestPhase8EpubEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(API_ROOT, exist_ok=True)
        cls.test_db = JobDatabase(db_path=os.path.join(API_ROOT, "jobs.db"))

    def setUp(self):
        self.job_id = "epub_api_" + uuid.uuid4().hex[:12]
        self.test_db.create_job(
            job_id=self.job_id,
            filename="หนังสือทดสอบ.pdf",
            file_path=os.path.join(API_ROOT, "input.pdf"),
            file_size_bytes=1024,
            total_pages=2,
            enable_ai=False,
        )
        job_dir = os.path.join(API_ROOT, self.job_id)
        os.makedirs(job_dir, exist_ok=True)
        for page in (1, 2):
            page_dir = os.path.join(job_dir, f"page_{page:02d}")
            os.makedirs(page_dir, exist_ok=True)
            with open(os.path.join(page_dir, "final.txt"), "w", encoding="utf-8") as stream:
                stream.write(f"บทที่ {page} หน้า {page}\nเนื้อหาภาษาไทยหน้า {page}")
        with open(os.path.join(job_dir, "final.txt"), "w", encoding="utf-8") as stream:
            stream.write("บทที่ 1 หน้า 1\nเนื้อหาภาษาไทยหน้า 1\fบทที่ 2 หน้า 2\nเนื้อหาภาษาไทยหน้า 2")

        self.patch_dir = patch("src.server.DEFAULT_OUTPUT_DIR", API_ROOT)
        self.patch_db = patch("src.server.db", self.test_db)
        self.patch_dir.start()
        self.patch_db.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.patch_db.stop()
        self.patch_dir.stop()

    def test_preview_package_status_and_download(self):
        html_res = self.client.post(f"/api/jobs/{self.job_id}/export/html", json={"mode": "basic"})
        self.assertEqual(html_res.status_code, 200)

        preview_res = self.client.post(
            f"/api/jobs/{self.job_id}/export/epub/preview",
            json={
                "source_variant": "basic",
                "chapter_split": "page",
                "metadata": {"title": "หนังสือทดสอบ", "language": "th"},
            },
        )
        self.assertEqual(preview_res.status_code, 200)
        revision = preview_res.json()["meta"]["preview_revision"]

        preview_get = self.client.get(f"/api/jobs/{self.job_id}/export/epub/preview")
        self.assertEqual(preview_get.status_code, 200)
        self.assertIn("sandbox", preview_get.headers.get("content-security-policy", ""))
        self.assertEqual(preview_get.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("หนังสือทดสอบ", preview_get.text)

        conflict = self.client.post(
            f"/api/jobs/{self.job_id}/export/epub",
            json={"base_preview_revision": "wrong"},
        )
        self.assertEqual(conflict.status_code, 409)

        package_res = self.client.post(
            f"/api/jobs/{self.job_id}/export/epub",
            json={"base_preview_revision": revision},
        )
        self.assertEqual(package_res.status_code, 200)
        self.assertTrue(package_res.json()["meta"]["validation"]["valid"])

        status_res = self.client.get(f"/api/jobs/{self.job_id}/export/epub/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["status"], "ready")
        self.assertTrue(status_res.json()["epub_ready"])

        download = self.client.get(f"/api/jobs/{self.job_id}/export/epub/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("filename*=UTF-8''", download.headers.get("content-disposition", ""))
        self.assertEqual(download.content[:2], b"PK")


if __name__ == "__main__":
    unittest.main()
