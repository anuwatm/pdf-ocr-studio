"""Phase 8.1 Chrome/Edge comparison flow. Artifacts are retained."""

import os
import socket
import threading
import time
import unittest
import uuid

import uvicorn
from playwright.sync_api import sync_playwright

from src.database import JobDatabase
from src.file_utils import atomic_write_text
from src.job_models import JobStatus, PageStatus, StageStatus
from src.pipeline import ProcessingPipeline
import src.server as server_module


RUNTIME = os.path.abspath("tests/artifacts/phase8_1_browser")
DEMO_DIR = "demo" if os.path.isdir("demo") else os.path.abspath(os.path.join("..", "demo"))


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestPhase81Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(RUNTIME, exist_ok=True)
        cls.job_id = "phase81_browser_" + uuid.uuid4().hex[:10]
        cls.job_dir = os.path.join(RUNTIME, cls.job_id)
        demo04 = os.path.join(DEMO_DIR, "04.pdf")
        result = ProcessingPipeline(ocr_engine=object()).process_file(
            demo04, job_id=cls.job_id, output_dir=cls.job_dir, page_range=[1]
        )
        page_dir = os.path.join(cls.job_dir, "page_01")
        os.makedirs(page_dir, exist_ok=True)
        atomic_write_text(os.path.join(page_dir, "raw.txt"), result["pages"][0]["raw_text"])
        atomic_write_text(os.path.join(page_dir, "corrected.txt"), result["pages"][0]["raw_text"] + "\nAI corrected marker")
        atomic_write_text(os.path.join(page_dir, "final.txt"), result["pages"][0]["raw_text"] + "\nmanual final marker")

        cls.database = JobDatabase(os.path.join(RUNTIME, "jobs.db"))
        cls.database.create_job(cls.job_id, "04.pdf", os.path.abspath(demo04),
                                os.path.getsize(demo04), 1, False)
        cls.database.update_page_progress(cls.job_id, 1, PageStatus.COMPLETED,
                                          StageStatus.COMPLETED, StageStatus.SKIPPED, 1,
                                          raw_text_length=len(result["pages"][0]["raw_text"]))
        cls.database.update_job_status(cls.job_id, JobStatus.COMPLETED)
        cls.original_db = server_module.db
        cls.original_output = server_module.DEFAULT_OUTPUT_DIR
        server_module.db = cls.database
        server_module.DEFAULT_OUTPUT_DIR = RUNTIME

        cls.port = free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.allowed_host = f"127.0.0.1:{cls.port}"
        server_module.ALLOWED_HOSTS.add(cls.allowed_host)
        server_module.ALLOWED_ORIGINS.add(cls.base_url)
        cls.server = uvicorn.Server(uvicorn.Config(server_module.app, host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Phase 8.1 browser server did not start")
        cls.playwright = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.playwright.stop()
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        server_module.db = cls.original_db
        server_module.DEFAULT_OUTPUT_DIR = cls.original_output
        server_module.ALLOWED_HOSTS.discard(cls.allowed_host)
        server_module.ALLOWED_ORIGINS.discard(cls.base_url)

    def run_flow(self, channel):
        browser = self.playwright.chromium.launch(channel=channel, headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        external = []
        console_errors = []
        page.on("request", lambda request: external.append(request.url)
                if not request.url.startswith(self.base_url) and not request.url.startswith("about:") else None)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        try:
            response = page.goto(self.base_url + "/", wait_until="domcontentloaded")
            self.assertIsNotNone(response)
            self.assertEqual(response.status, 200, page.content()[:500])
            page.wait_for_selector('[data-main-tab="history"]', timeout=10000)
            page.click('[data-main-tab="history"]')
            page.locator(f'[data-history-open="{self.job_id}"]').click()
            page.wait_for_selector("#section-workspace:not(.hidden)")
            page.click('[data-main-tab="structured"]')
            page.click("#btn-generate-structured")
            page.wait_for_selector("#structured-status-badge.badge-success", timeout=15000)
            page.wait_for_selector("#structured-source-image[src*='/pages/1/image']")
            frame = page.frame_locator("#structured-preview-frame")
            first_cell = frame.locator("td").first
            first_cell.click()
            page.wait_for_selector("#structured-bbox-overlay rect")
            self.assertEqual(page.locator("#structured-page-select option").count(), 1)
            page.select_option("#structured-result-mode", "corrected")
            self.assertIn("AI corrected marker", frame.locator("pre").text_content())
            page.select_option("#structured-result-mode", "final")
            self.assertIn("manual final marker", frame.locator("pre").text_content())
            page.select_option("#structured-result-mode", "raw")
            self.assertNotIn("manual final marker", frame.locator("pre").text_content())
            page.select_option("#structured-result-mode", "html")
            frame.locator("td").first.wait_for()
            self.assertIn("/export/structured/text", page.get_attribute("#btn-dl-structured-text", "href"))
            with page.expect_download() as downloading:
                page.click("#btn-dl-structured-text")
            self.assertTrue(downloading.value.suggested_filename.endswith("structured.txt"))

            edit = page.evaluate("""async job=>{const d=await(await fetch(`/api/jobs/${job}/pages/1/data`)).json();
              const r=await fetch(`/api/jobs/${job}/pages/1/edit`,{method:'PUT',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({source_revision:d.revision,edited_text:d.final_text+'\\nแก้ไข Phase 8.1'})});return {status:r.status,body:await r.json()};}""", self.job_id)
            self.assertEqual(edit["status"], 200)
            page.click('[data-main-tab="progress"]')
            page.click('[data-main-tab="structured"]')
            page.wait_for_function("document.getElementById('structured-status-badge').textContent.includes('ล้าสมัย')")
            self.assertTrue(page.locator("#btn-dl-structured-text").evaluate("node=>node.classList.contains('hidden')"))
            page.click("#btn-generate-structured")
            page.wait_for_selector("#structured-status-badge.badge-success", timeout=15000)
            self.assertEqual(external, [])
            self.assertEqual(console_errors, [])

            page.set_viewport_size({"width": 390, "height": 844})
            page.click("#btn-structured-mobile-result")
            self.assertTrue(page.locator("#structured-source-pane").evaluate("node => node.classList.contains('structured-mobile-hidden')"))
            first_cell.focus()
            first_cell.press("Enter")
            self.assertEqual(page.locator("#structured-bbox-overlay rect").count(), 1)
        finally:
            context.close()
            browser.close()

    def test_chrome(self):
        self.run_flow("chrome")

    def test_edge(self):
        self.run_flow("msedge")


if __name__ == "__main__":
    unittest.main()
