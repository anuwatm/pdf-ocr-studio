"""
Phase 7 Test 5: API Endpoints, Sandboxed Preview, RFC 5987 Downloads, and Conflict 409.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.server import app, db, job_manager, DEFAULT_OUTPUT_DIR
from src.database import JobDatabase
from src.job_models import JobStatus


class TestExportEndpointsAndConflicts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.job_id = "job_api_export_test"

        # Create job in DB
        db.create_job(
            job_id=self.job_id,
            filename="export_doc.pdf",
            file_path="files/export_doc.pdf",
            file_size_bytes=1024,
            total_pages=2,
            enable_ai=False,
        )

        # Setup mock files in DEFAULT_OUTPUT_DIR
        self.job_dir = os.path.join(DEFAULT_OUTPUT_DIR, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)
        for p in (1, 2):
            pd = os.path.join(self.job_dir, f"page_{p:02d}")
            os.makedirs(pd, exist_ok=True)
            with open(os.path.join(pd, "final.txt"), "w", encoding="utf-8") as f:
                f.write(f"เนื้อหาหน้า {p} สำหรับทดสอบ API Export\n")
        with open(os.path.join(self.job_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("เนื้อหาหน้า 1 สำหรับทดสอบ API Export\n\f\nเนื้อหาหน้า 2 สำหรับทดสอบ API Export\n")

    def tearDown(self):
        db.delete_job(self.job_id)
        shutil.rmtree(self.job_dir, ignore_errors=True)

    def test_01_export_basic_and_status(self):
        """POST export/html creates basic.html and GET status reports ready."""
        # 1. Initially status is not_generated
        r_init = self.client.get(f"/api/jobs/{self.job_id}/export/html/status")
        self.assertEqual(r_init.status_code, 200)
        self.assertFalse(r_init.json().get("has_basic"))

        # 2. POST create basic export
        r_post = self.client.post(f"/api/jobs/{self.job_id}/export/html", json={"mode": "basic"})
        self.assertEqual(r_post.status_code, 200)
        self.assertEqual(r_post.json().get("status"), "ready")

        # 3. Status is now ready
        r_status = self.client.get(f"/api/jobs/{self.job_id}/export/html/status")
        self.assertEqual(r_status.status_code, 200)
        self.assertTrue(r_status.json().get("has_basic"))
        self.assertFalse(r_status.json().get("is_stale"))

    def test_02_download_has_nosniff_and_rfc5987(self):
        """GET export/html/{variant} download returns attachment with nosniff and UTF-8 filename."""
        self.client.post(f"/api/jobs/{self.job_id}/export/html", json={"mode": "basic"})

        r_dl = self.client.get(f"/api/jobs/{self.job_id}/export/html/basic")
        self.assertEqual(r_dl.status_code, 200)
        self.assertEqual(r_dl.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("attachment", r_dl.headers.get("content-disposition", ""))
        self.assertIn("filename*=", r_dl.headers.get("content-disposition", ""))

    def test_03_preview_has_csp_sandbox(self):
        """GET export/html/{variant}/preview returns CSP with sandbox."""
        self.client.post(f"/api/jobs/{self.job_id}/export/html", json={"mode": "basic"})

        r_prev = self.client.get(f"/api/jobs/{self.job_id}/export/html/basic/preview")
        self.assertEqual(r_prev.status_code, 200)
        csp = r_prev.headers.get("content-security-policy", "")
        self.assertIn("sandbox", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertEqual(r_prev.headers.get("x-content-type-options"), "nosniff")

    def test_04_save_final_conflict_409_and_overwrite(self):
        """PUT export/html/final enforces base_revision and returns 409 on conflict."""
        self.client.post(f"/api/jobs/{self.job_id}/export/html", json={"mode": "basic"})
        status_res = self.client.get(f"/api/jobs/{self.job_id}/export/html/status").json()
        correct_rev = status_res.get("source_revision")

        # 1. Conflicting base_revision returns 409
        r_conf = self.client.put(
            f"/api/jobs/{self.job_id}/export/html/final",
            json={"html_content": "<p>User Edit</p>", "base_revision": "wrong_old_revision", "overwrite": False},
        )
        self.assertEqual(r_conf.status_code, 409)

        # 2. Correct base_revision succeeds
        r_ok = self.client.put(
            f"/api/jobs/{self.job_id}/export/html/final",
            json={"html_content": "<p>User Edit</p>", "base_revision": correct_rev, "overwrite": False},
        )
        self.assertEqual(r_ok.status_code, 200)
        self.assertEqual(r_ok.json().get("status"), "saved")

        # 3. Overwrite=True succeeds even with different base_revision
        r_over = self.client.put(
            f"/api/jobs/{self.job_id}/export/html/final",
            json={"html_content": "<p>Overwritten Edit</p>", "base_revision": "outdated_rev", "overwrite": True},
        )
        self.assertEqual(r_over.status_code, 200)


if __name__ == "__main__":
    unittest.main()
