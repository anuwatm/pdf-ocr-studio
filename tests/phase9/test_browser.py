import io
import base64
import mimetypes
import os
import unittest
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from src.database import JobDatabase
from src.server import app


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "tests/artifacts/phase9_browser"
SOURCE = """<html><body><h1 id="intro">บทนำ</h1><p>เนื้อหา</p>
<h2 id="same-a">ชื่อซ้ำ</h2><p>ก</p><h2 id="same-b">ชื่อซ้ำ</h2><p>ข</p>
<h1 id="end">สรุป &amp; จบ</h1><p>ท้ายเรื่อง</p></body></html>"""


class TestPhase9Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.database = JobDatabase(str(ARTIFACTS / "jobs.db"))
        cls.cover = ARTIFACTS / "cover.png"
        Image.new("RGB", (120, 180), "navy").save(cls.cover, "PNG")
        cls.playwright = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.playwright.stop()

    def run_flow(self, channel):
        job_id = "toc_" + channel
        if not self.database.get_job_status(job_id):
            self.database.create_job(job_id, "toc.pdf", "fixture.pdf", 10, 1, False)
        export = ARTIFACTS / job_id / "export"
        export.mkdir(parents=True, exist_ok=True)
        (export / "basic.html").write_text(SOURCE, encoding="utf-8")
        job = {"job_id":job_id,"filename":"toc.pdf","total_pages":1,"completed_pages":1,
               "failed_pages":0,"status":"completed","current_attempt":1,"file_size_bytes":10,
               "updated_at":"2026-10-06T10:00:00","pages":[{"page_id":1,"page_num":1,"status":"completed"}]}
        external, errors = [], []
        with patch("src.server.db", self.database), patch("src.server.DEFAULT_OUTPUT_DIR", str(ARTIFACTS)):
            client = TestClient(app)
            markup = client.get("/").text
            browser = self.playwright.chromium.launch(channel=channel, headless=True)
            context = browser.new_context(accept_downloads=True, viewport={"width":1280,"height":900})

            def route_request(route):
                parsed = urlparse(route.request.url)
                if parsed.hostname not in {"127.0.0.1", "localhost"}:
                    external.append(route.request.url); return route.abort()
                path = parsed.path + (("?" + parsed.query) if parsed.query else "")
                if parsed.path == "/": return route.fulfill(body=markup, content_type="text/html")
                if parsed.path.startswith("/static/"):
                    file = ROOT / parsed.path.lstrip("/")
                    return route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file.name)[0] or "text/plain")
                if "/export/epub" in parsed.path:
                    response = client.request(route.request.method, path, content=route.request.post_data,
                                              headers={"Content-Type":"application/json"})
                    return route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
                if parsed.path == "/api/jobs": return route.fulfill(json=[job])
                if parsed.path.endswith("/export/html/status"): return route.fulfill(json={"variants":[]})
                if parsed.path.endswith("/export/html/ai/progress"): return route.fulfill(json={"status":"idle"})
                if parsed.path.endswith("/status") and "/jobs/" in parsed.path: return route.fulfill(json=job)
                if parsed.path.endswith("/data"): return route.fulfill(json={"reference_image":{"url":""},"raw_text":"","final_text":"","revision":1})
                return route.fulfill(json={"status":"offline"})

            context.route("**/*", route_request)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("window.__alerts=[];window.alert=x=>window.__alerts.push(String(x));window.confirm=()=>true")
            try:
                page.goto("http://127.0.0.1:8000/")
                page.locator('[data-main-tab="history"]').click()
                page.locator('[data-history-open]').click()
                page.locator('[data-main-tab="epub"]').click()
                page.locator("#btn-load-epub-toc").click()
                expect(page.locator(".toc-row")).to_have_count(4)
                first = page.locator(".toc-row").first
                first.locator("input").fill("บทนำฉบับแก้ <ปลอดภัย>")
                page.evaluate("window.confirm=()=>false")
                page.locator("#btn-load-epub-toc").click()
                self.assertEqual(first.locator("input").input_value(), "บทนำฉบับแก้ <ปลอดภัย>")
                page.evaluate("window.confirm=()=>true")
                first.get_by_role("button", name="เลื่อนลง").click()
                page.locator(".toc-row").nth(1).get_by_role("button", name="เพิ่มระดับ").click()
                page.locator("#btn-add-epub-toc").click()
                expect(page.locator(".toc-row")).to_have_count(5)
                page.locator(".toc-row").last.get_by_role("button", name="เอารายการออก").click()
                page.locator("#btn-save-epub-toc").click()
                expect(page.locator("#btn-build-epub")).to_be_enabled(timeout=10000)
                expect(page.frame_locator("#epub-preview-frame").locator("nav")).to_contain_text("บทนำฉบับแก้ <ปลอดภัย>")
                page.locator("#btn-load-epub-toc").click()
                page.wait_for_function("[...document.querySelectorAll('.toc-row input')].some(x=>x.value.includes('บทนำฉบับแก้'))")

                encoded = base64.b64encode(self.cover.read_bytes()).decode()
                page.evaluate("""value=>{const bytes=Uint8Array.from(atob(value),c=>c.charCodeAt(0));
                  const file=new File([bytes],'cover.png',{type:'image/png'});const dt=new DataTransfer();dt.items.add(file);
                  document.getElementById('epub-cover-drop').dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));}""", encoded)
                expect(page.locator("#epub-cover-thumbnail")).to_be_visible()
                expect(page.locator("#epub-cover-details")).to_contain_text("120×180")
                expect(page.locator("#btn-build-epub")).to_be_disabled()
                page.locator("#btn-generate-epub-preview").click()
                expect(page.locator("#btn-build-epub")).to_be_enabled(timeout=10000)
                with page.expect_download(): page.locator("#btn-build-epub").click()

                page.set_viewport_size({"width":390,"height":844})
                page.locator(".toc-row input").first.focus()
                page.locator(".toc-row input").first.press("Control+A")
                page.locator(".toc-row input").first.type("มือถือ")
                expect(page.locator("#btn-save-epub-toc")).to_be_enabled()
                self.assertEqual(external, [])
                self.assertEqual(errors, [])
            finally:
                context.close(); browser.close()

    def test_chrome(self): self.run_flow("chrome")
    def test_edge(self): self.run_flow("msedge")


if __name__ == "__main__":
    unittest.main()
