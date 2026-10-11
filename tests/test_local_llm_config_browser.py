import json
import mimetypes
import unittest
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.sync_api import expect, sync_playwright
    PLAYWRIGHT_AVAILABLE=True
except ImportError:
    PLAYWRIGHT_AVAILABLE=False

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE,"playwright is available")
class LocalLLMConfigBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.playwright=sync_playwright().start()
    @classmethod
    def tearDownClass(cls): cls.playwright.stop()

    def run_flow(self,channel):
        browser=self.playwright.chromium.launch(channel=channel,headless=True)
        context=browser.new_context();page=context.new_page();requests=[];errors=[];cli_status_requests=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        def route_request(route):
            path=urlparse(route.request.url).path
            if path=="/config.html":return route.fulfill(body=(ROOT/"static"/"config.html").read_bytes(),content_type="text/html")
            if path.startswith("/static/"):
                file=ROOT/path.lstrip("/");return route.fulfill(body=file.read_bytes(),content_type=mimetypes.guess_type(file.name)[0] or "text/plain")
            if path=="/api/ai/config":
                if route.request.method=="PUT":
                    payload=json.loads(route.request.post_data);requests.append(payload);return route.fulfill(json={**payload,"api_key_configured":False})
                return route.fulfill(json={"transport":"api","base_url":"http://127.0.0.1:1234/v1","model":"google/gemma-4-e2b","timeout":60,"api_key_configured":False,"cli_provider":"codex"})
            if path=="/api/ai/config/test":
                payload=json.loads(route.request.post_data);requests.append(payload)
                return route.fulfill(json={"status":"connected","transport":payload["transport"],"cli_provider":payload["cli_provider"],"configured_model":payload["model"],"model_found":True})
            if path=="/api/ai/cli/status":
                cli_status_requests.append((route.request.method,path))
                return route.fulfill(json={"checked_at":"2026-10-09T12:00:00+00:00","adapters":[
                    {"id":"codex","label":"Codex CLI","primary":True,"installed":True,"command":"codex","version":"codex-cli 0.150.1","status":"ready","authentication":"ready","local_runtime":"supported","detail":"พร้อมใช้งาน"},
                    {"id":"gemini","label":"Gemini CLI","primary":True,"installed":True,"command":"gemini","version":"0.41.2","status":"ready","authentication":"check_on_use","local_runtime":"not_ready","detail":"ติดตั้งแล้ว; cloud auth ตรวจเมื่อเรียกใช้งาน"},
                    {"id":"agy","label":"AGY CLI","primary":True,"installed":True,"command":"agy","version":"1.3.2","status":"ready","authentication":"check_on_use","local_runtime":"not_supported","detail":"ติดตั้งแล้ว"},
                    {"id":"claude","label":"Claude CLI","primary":True,"installed":False,"command":"claude","version":None,"status":"not_installed","authentication":"not_checked","local_runtime":"not_checked","detail":"ไม่พบคำสั่งใน PATH"},
                    {"id":"lms","label":"LM Studio CLI","primary":False,"installed":False,"command":"lms","version":None,"status":"not_installed","authentication":"not_checked","local_runtime":"not_checked","detail":"ไม่พบคำสั่งใน PATH"}
                ]})
            if path=="/api/ai/cli/status/check":
                cli_status_requests.append((route.request.method,path))
                return route.fulfill(json={"checked_at":"2026-10-09T12:00:00+00:00","adapters":[
                    {"id":"codex","label":"Codex CLI","primary":True,"installed":True,"command":"codex","version":"codex-cli 0.150.1","status":"ready","authentication":"ready","local_runtime":"supported","detail":"พร้อมใช้งาน"},
                    {"id":"gemini","label":"Gemini CLI","primary":True,"installed":True,"command":"gemini","version":"0.41.2","status":"ready","authentication":"check_on_use","local_runtime":"not_ready","detail":"ติดตั้งแล้ว; cloud auth ตรวจเมื่อเรียกใช้งาน"},
                    {"id":"agy","label":"AGY CLI","primary":True,"installed":True,"command":"agy","version":"1.3.2","status":"ready","authentication":"check_on_use","local_runtime":"not_supported","detail":"ติดตั้งแล้ว"},
                    {"id":"claude","label":"Claude CLI","primary":True,"installed":False,"command":"claude","version":None,"status":"not_installed","authentication":"not_checked","local_runtime":"not_checked","detail":"ไม่พบคำสั่งใน PATH"},
                    {"id":"lms","label":"LM Studio CLI","primary":False,"installed":False,"command":"lms","version":None,"status":"not_installed","authentication":"not_checked","local_runtime":"not_checked","detail":"ไม่พบคำสั่งใน PATH"}
                ]})
            if path=="/api/translation/google/config":
                return route.fulfill(json={"project":"","location":"global","credentials_path":"","credentials_configured":False,"api_key_configured":False})
            return route.fulfill(status=404,json={"detail":"not found"})
        context.route("**/*",route_request)
        try:
            page.goto("http://127.0.0.1:8000/config.html")
            expect(page.locator('[data-adapter="codex"]')).to_contain_text("พร้อมใช้งาน")
            expect(page.locator('[data-adapter="gemini"]')).to_contain_text("ตรวจเมื่อใช้งาน")
            expect(page.locator('[data-adapter="agy"]')).to_contain_text("1.3.2")
            expect(page.locator('[data-adapter="claude"]')).to_contain_text("ไม่พบโปรแกรม")
            expect(page.locator('[data-adapter="lms"]')).to_contain_text("ไม่พบโปรแกรม")
            expect(page.locator("#cli-status-summary")).to_contain_text("ตรวจพบ 3/5")
            page.locator("#btn-refresh-cli-status").click()
            expect(page.locator("#cli-status-list")).to_have_attribute("aria-busy","false")
            page.locator("#llm-transport").select_option("cli")
            expect(page.locator("#llm-base-url-field")).to_be_hidden();expect(page.locator("#llm-cli-provider-field")).to_be_visible();expect(page.locator("#llm-cli-notice")).to_be_visible()
            page.locator("#llm-cli-provider").select_option("agy")
            expect(page.locator("#llm-cli-provider")).to_have_value("agy")
            page.locator("#llm-cli-provider").select_option("claude")
            page.locator("#btn-test-connection").click();expect(page.locator("#config-result")).to_contain_text("เชื่อมต่อสำเร็จ (CLAUDE CLI)")
            page.locator("#btn-save-config").click();expect(page.locator("#config-result")).to_contain_text("บันทึกแล้ว")
            self.assertTrue(all(item["transport"]=="cli" and item["cli_provider"]=="claude" for item in requests));self.assertEqual(cli_status_requests,[("GET","/api/ai/cli/status"),("POST","/api/ai/cli/status/check")]);self.assertEqual(errors,[])
        finally: context.close();browser.close()

    def test_chrome(self): self.run_flow("chrome")
    def test_edge(self): self.run_flow("msedge")


if __name__=="__main__": unittest.main()
