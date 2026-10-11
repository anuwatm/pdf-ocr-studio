import json
import mimetypes
import unittest
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient
try:
    from playwright.sync_api import expect, sync_playwright
    PLAYWRIGHT_AVAILABLE=True
except ImportError:
    PLAYWRIGHT_AVAILABLE=False

from src.server import app

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE,"playwright is available in publish/venv")
class Phase10BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright=sync_playwright().start()

    @classmethod
    def tearDownClass(cls): cls.playwright.stop()

    def run_flow(self,channel):
        client=TestClient(app);markup=client.get("/").text
        job={"job_id":"translation_browser","filename":"book.pdf","total_pages":2,"completed_pages":2,
             "failed_pages":0,"status":"completed","current_attempt":1,"file_size_bytes":100,
             "updated_at":"2026-10-09T10:00:00","pages":[]}
        model={"schema_version":"10.0","job_id":job["job_id"],"status":"completed","stale":False,
            "translation_revision":"rev-1","detected_language":"en","language_confidence":.98,"warnings":[],
            "segments":[
                {"id":"s1","type":"p","page":1,"source_text":"OpenAI costs $20","baseline_text":"OpenAI ราคา $20","translated_text":"OpenAI มีราคา $20","final_text":"OpenAI มีราคา $20","status":"translated","warnings":[]},
                {"id":"s2","type":"p","page":2,"source_text":"Second page","baseline_text":"หน้าที่สอง","translated_text":"หน้าสอง","final_text":"หน้าสอง","status":"translated","warnings":[]}]}
        external=[];errors=[];started=False;saved=[]
        browser=self.playwright.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={"width":1280,"height":900})

        def route_request(route):
            nonlocal started
            parsed=urlparse(route.request.url);path=parsed.path
            if parsed.hostname not in {"127.0.0.1","localhost"}: external.append(route.request.url);return route.abort()
            if path=="/": return route.fulfill(body=markup,content_type="text/html")
            if path.startswith("/static/"):
                file=ROOT/path.lstrip("/");return route.fulfill(body=file.read_bytes(),content_type=mimetypes.guess_type(file.name)[0] or "text/plain")
            if path=="/api/jobs": return route.fulfill(json=[job])
            if path=="/api/upload": return route.fulfill(json={**job,"job_id":"auto_count_image","filename":"01.png","total_pages":1})
            if path=="/api/ai/cli/status": return route.fulfill(json={"checked_at":"2026-10-10T08:00:00+00:00","adapters":[
                {"id":"codex","label":"Codex CLI","status":"ready"},{"id":"gemini","label":"Gemini CLI","status":"not_installed"}]})
            if path.endswith("/status") and "/jobs/" in path: return route.fulfill(json=job)
            if path.endswith("/data"): return route.fulfill(json={"reference_image":{"url":""},"raw_text":"","final_text":"","revision":1})
            if path.endswith("/export/html/status"): return route.fulfill(json={"variants":[{"variant":"final"}]})
            if path.endswith("/export/html/ai/progress"): return route.fulfill(json={"status":"idle"})
            if path=="/api/translation/capabilities": return route.fulfill(json={"prompt_version":"10.0.0","styles":{},"providers":[
                {"provider":"local_api","label":"Local LLM API","cloud":False,"available":True,"languages":[{"code":"en","name":"English"},{"code":"th","name":"ไทย"}]},
                {"provider":"cli_codex","label":"Codex CLI","cloud":True,"available":True,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"cli_gemini","label":"Gemini CLI","cloud":True,"available":True,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"cli_agy","label":"AGY CLI","cloud":True,"available":True,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"cli_claude","label":"Claude CLI","cloud":True,"available":False,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"cli_lms","label":"LM Studio CLI","cloud":False,"available":True,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"google","label":"Google Cloud Translation","cloud":True,"available":True,"languages":[{"code":"th","name":"ไทย"}]},
                {"provider":"hybrid","label":"Hybrid","cloud":True,"available":True,"languages":[{"code":"th","name":"ไทย"}]}]})
            if path.endswith("/translation/glossary"):
                if route.request.method=="PUT": return route.fulfill(json={"revision":"g2","entries":json.loads(route.request.post_data)["entries"]})
                return route.fulfill(json={"revision":"g1","entries":[]})
            if path.endswith("/translation/estimate"): return route.fulfill(json={"characters":40,"batch_count":2,"cloud":False,"estimated_cost":0,"currency":"USD"})
            if path.endswith("/translation/start"): started=True;return route.fulfill(status=202,json={"status":"queued","batch_count":2,"completed_batches":0,"total_segments":2,"completed_segments":0})
            if path.endswith("/translation/progress"):
                return route.fulfill(json={"status":"completed" if started else "idle","batch_count":2,"completed_batches":2 if started else 0,"total_segments":2,"completed_segments":2 if started else 0,"elapsed_seconds":.2})
            if path.endswith("/translation/result"):
                response={**model,"stale":bool(saved),"stale_reasons":["glossary_revision_changed"] if saved else []}
                return route.fulfill(json=response)
            if path.endswith("/translation/final"):
                saved.append(json.loads(route.request.post_data));return route.fulfill(json={**model,"translation_revision":"rev-2"})
            if path.endswith("/translation/preview"): return route.fulfill(body="<html><body>translated</body></html>",content_type="text/html")
            if path.endswith("/translation/source/preview"): return route.fulfill(body="<html><body>source preview</body></html>",content_type="text/html")
            return route.fulfill(json={"status":"offline"})

        context.route("**/*",route_request);page=context.new_page();page.on("pageerror",lambda e:errors.append(str(e)))
        page.add_init_script("window.__alerts=[];window.alert=x=>window.__alerts.push(String(x));window.confirm=()=>true;window.prompt=()=>''")
        try:
            page.goto("http://127.0.0.1:8000/")
            expect(page.locator("#include-page-numbers")).not_to_be_checked()
            expect(page.locator("#cli-header-status-text")).to_have_text("AI CLI: Codex")
            page.locator("#file-input").set_input_files({"name":"01.png","mimeType":"image/png","buffer":b"fixture"})
            expect(page.locator("#page-options")).to_be_visible();expect(page.locator("#pdf-page-summary")).to_have_text("เอกสารนี้มี 1 หน้า")
            page.locator('[data-main-tab="history"]').click();page.locator('[data-history-open]').click()
            page.locator('[data-main-tab="translation"]').click();expect(page.locator("#translation-target-language")).to_have_value("th")
            self.assertEqual(page.locator("#translation-source option").all_text_contents(),["อัตโนมัติ (HTML ก่อน Text)","final.html","structured.html","ai.html","basic.html","final.txt","corrected.txt","raw.txt"])
            self.assertEqual(page.locator("#translation-provider option").count(),8)
            with page.expect_popup() as popup_info: page.locator("#btn-view-translation-source").click()
            popup=popup_info.value;self.assertIn("/translation/source/preview?source_variant=auto",popup.url);popup.close()
            page.locator("#translation-style").select_option("academic");page.locator("#btn-estimate-translation").click()
            expect(page.locator("#translation-estimate")).to_contain_text("40 อักขระ")
            page.locator("#btn-start-translation").click();expect(page.locator(".translation-segment")).to_have_count(2,timeout=10000)
            combined=page.locator("#translation-combined-text");expect(combined).to_have_value("OpenAI มีราคา $20\n\nหน้าสอง")
            expect(page.locator("#translation-combined-summary")).to_contain_text("2 segment")
            expect(page.locator("#btn-download-translation-text")).to_have_attribute("href",f"/api/jobs/{job['job_id']}/translation/export/text")
            expect(page.locator("#btn-download-translation-html")).to_have_attribute("href",f"/api/jobs/{job['job_id']}/translation/export/html")
            page.locator("#translation-review-mode").select_option("google");expect(page.locator(".translation-segment").first.locator("pre").nth(1)).to_contain_text("Google baseline")
            page.locator("#translation-page-filter").select_option("1");editor=page.locator("[data-final]");editor.fill("draft manual")
            expect(combined).to_have_value("draft manual\n\nหน้าสอง")
            page.locator("#translation-page-filter").select_option("2");expect(combined).to_have_value("draft manual\n\nหน้าสอง");page.locator("#translation-page-filter").select_option("1");expect(page.locator("[data-final]")).to_have_value("draft manual")
            page.locator("#btn-save-translation-final").click();expect(page.locator("#translation-language-status")).to_contain_text("stale:")
            self.assertTrue(any(edit["id"]=="s1" and edit["text"]=="draft manual" for edit in saved[0]["edits"]))
            page.locator("#translation-provider").select_option("cli_codex");expect(page.locator("#translation-consent-text")).to_have_text("ยินยอมส่งข้อความ segment ไป Cloud AI ผ่าน Codex CLI");page.locator("#btn-start-translation").click();self.assertIn("กรุณาติ๊กยินยอม",page.evaluate("window.__alerts.at(-1)"))
            page.locator("#translation-provider").select_option("google");expect(page.locator("#translation-consent-wrap")).to_be_visible();expect(page.locator("#translation-cloud-consent")).not_to_be_checked();expect(page.locator("#translation-consent-text")).to_have_text("ยินยอมส่งข้อความ segment ไป Cloud AI ผ่าน Google Cloud Translation");page.locator("#translation-cloud-consent").check();page.locator("#btn-start-translation").click()
            page.set_viewport_size({"width":390,"height":844});page.locator("#translation-glossary-editor").focus();page.locator("#translation-glossary-editor").press("Tab")
            self.assertEqual(external,[]);self.assertEqual(errors,[])
        finally:
            context.close();browser.close()

    def test_chrome(self): self.run_flow("chrome")
    def test_edge(self): self.run_flow("msedge")


if __name__=="__main__": unittest.main()
