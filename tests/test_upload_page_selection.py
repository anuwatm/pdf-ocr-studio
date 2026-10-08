"""Tests the upload page-count flow with approved demo PDFs only."""
import os
import shutil
import json
import zipfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.server import app, db, job_manager, DEFAULT_OUTPUT_DIR
from src.job_models import PageStatus, StageStatus
from src.worker_process import _iter_page_batches

DEMO_DIR = "demo" if os.path.isdir("demo") else os.path.abspath(os.path.join("..", "demo"))


class TestUploadPageSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls._spawn_patcher = patch.object(job_manager, "_spawn_worker_subprocess", return_value=None)
        cls._spawn_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._spawn_patcher.stop()

    def tearDown(self):
        import gc, time
        gc.collect()
        # Every test-created upload is removed from the real files/ workspace.
        for job_id in getattr(self, "created_jobs", []):
            db.delete_job(job_id)
            target = os.path.join(DEFAULT_OUTPUT_DIR, job_id)
            for _ in range(5):
                if not os.path.exists(target):
                    break
                shutil.rmtree(target, ignore_errors=True)
                if os.path.exists(target):
                    time.sleep(0.05)
                    gc.collect()

    def _upload(self, filename: str) -> str:
        self.created_jobs = getattr(self, "created_jobs", [])
        with open(os.path.join(DEMO_DIR, filename), "rb") as source:
            response = self.client.post(
                "/api/upload",
                files={"file": (filename, source, "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["job_id"]
        self.created_jobs.append(job_id)
        return job_id

    def test_upload_reads_all_source_pages_and_stores_in_files(self):
        job_id = self._upload("06.pdf")
        status = self.client.get(f"/api/jobs/{job_id}/status").json()

        self.assertEqual(status["total_pages"], 569)
        path = os.path.abspath(db.get_job_raw_path(job_id))
        self.assertTrue(path.startswith(os.path.abspath(DEFAULT_OUTPUT_DIR)))
        self.assertTrue(os.path.isfile(path))

    def test_web_page_and_script_use_the_page_range_controls(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="input-page-start"', response.text)
        self.assertIn('id="input-page-end"', response.text)
        self.assertIn('/static/app.js?v=', response.text)
        self.assertIn('/static/app.css?v=', response.text)
        self.assertIn('id="btn-delete-all-history"', response.text)
        self.assertIn('id="include-page-numbers" type="checkbox" checked', response.text)
        self.assertIn('id="btn-test-ai-connection"', response.text)
        self.assertIn('id="mode-ocr-only" checked', response.text)
        self.assertIn('id="mode-ocr-ai" disabled', response.text)
        self.assertIn('id="btn-download-page-images"', response.text)
        self.assertIn('id="btn-start-job-html"', response.text)
        self.assertIn('id="btn-edit-structured-html"', response.text)
        self.assertIn('OCR เป็น HTML', response.text)
        script = self.client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("previewNewlyCompletedPage", script.text)
        self.assertIn('if (ext === ".pdf")', script.text)
        self.assertIn('startJobFlow("html")', script.text)
        self.assertIn('structuredWorkspace.generate()', script.text)
        self.assertIn('htmlWorkspace.loadStructuredHtml()', script.text)

    def test_api_schedules_more_than_one_batch(self):
        job_id = self._upload("06.pdf")
        with patch("src.server.job_manager.enqueue_job", return_value=True):
            response = self.client.post(
                f"/api/jobs/{job_id}/start",
                json={"enable_ai": False, "page_start": 1, "page_end": 201, "include_page_numbers": False},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["batch_size"], 200)
        self.assertEqual(response.json()["total_batches"], 2)
        status = self.client.get(f"/api/jobs/{job_id}/status").json()
        self.assertEqual(status["total_pages"], 201)
        self.assertEqual(status["total_batches"], 2)
        self.assertEqual(status["current_batch"], 1)
        options_path = os.path.join(DEFAULT_OUTPUT_DIR, job_id, "assembly_options.json")
        with open(options_path, "r", encoding="utf-8") as f:
            self.assertFalse(json.load(f)["include_page_numbers"])

    def test_worker_partitions_one_thousand_pages_into_five_batches(self):
        batches = list(_iter_page_batches(list(range(1, 1001))))
        self.assertEqual([len(batch) for batch in batches], [200, 200, 200, 200, 200])
        self.assertEqual(batches[0], list(range(1, 201)))
        self.assertEqual(batches[-1], list(range(801, 1001)))

    def test_selected_range_becomes_the_job_scope(self):
        job_id = self._upload("06.pdf")
        with patch("src.server.job_manager.enqueue_job", return_value=True):
            response = self.client.post(
                f"/api/jobs/{job_id}/start",
                json={"enable_ai": False, "page_start": 10, "page_end": 11},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["page_start"], 10)
        self.assertEqual(response.json()["page_end"], 11)
        status = self.client.get(f"/api/jobs/{job_id}/status").json()

        self.assertEqual(status["total_pages"], 2)
        self.assertEqual(len(status["pages"]), 2)
        self.assertEqual([page["page_id"] for page in status["pages"]], [10, 11])
        self.assertEqual([page["page_num"] for page in status["pages"]], [10, 11])
        self.assertFalse(status["enable_ai"])

    def test_cancel_assembles_completed_pages_and_marks_cancelled_pages(self):
        job_id = self._upload("06.pdf")
        page_dir = os.path.join(DEFAULT_OUTPUT_DIR, job_id, "page_01")
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "raw.txt"), "w", encoding="utf-8") as f:
            f.write("ข้อความ OCR หน้าที่หนึ่ง")
        with open(os.path.join(page_dir, "corrected.txt"), "w", encoding="utf-8") as f:
            f.write("ข้อความ OCR หน้าที่หนึ่ง")
        with open(os.path.join(page_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("ข้อความ OCR หน้าที่หนึ่ง")
        db.update_page_progress(
            job_id, 1, PageStatus.COMPLETED, StageStatus.COMPLETED,
            StageStatus.SKIPPED, attempt_number=1,
        )

        response = self.client.post(f"/api/jobs/{job_id}/cancel")
        self.assertEqual(response.status_code, 200, response.text)
        with open(os.path.join(DEFAULT_OUTPUT_DIR, job_id, "raw.txt"), "r", encoding="utf-8") as f:
            output = f.read()
        self.assertIn("ข้อความ OCR หน้าที่หนึ่ง", output)
        self.assertIn("[PAGE 2: CANCELLED]", output)

    def test_pdf_page_images_export_is_one_png_per_selected_page(self):
        job_id = self._upload("01.pdf")
        with patch("src.server.job_manager.enqueue_job", return_value=True):
            start = self.client.post(
                f"/api/jobs/{job_id}/start",
                json={"enable_ai": False, "page_start": 1, "page_end": 1},
            )
        self.assertEqual(start.status_code, 200, start.text)

        response = self.client.get(f"/api/jobs/{job_id}/download/page-images.zip")
        self.assertEqual(response.status_code, 200, response.text)
        zip_path = os.path.join(DEFAULT_OUTPUT_DIR, job_id, "page-images.zip")
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(zf.namelist(), ["page_0001.png"])
            self.assertGreater(len(zf.read("page_0001.png")), 100)
        response.close()


if __name__ == "__main__":
    unittest.main()
