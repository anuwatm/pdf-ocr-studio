"""Browser regression for AI success, precise failure, and fallback preview."""
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from src.server import app


def main():
    root = Path(__file__).resolve().parents[1]
    markup = TestClient(app).get('/').text
    job = dict(job_id='job_123456abcdef', filename='example.pdf', total_pages=1,
               completed_pages=1, failed_pages=0, status='completed', current_attempt=1,
               file_size_bytes=123, updated_at='2026-10-04T10:00:00',
               pages=[dict(page_id=1, page_num=1, status='completed')])
    task = {"status": "idle"}
    starts = []
    network_failure = False
    errors = []

    def route_request(route):
        path = urlparse(route.request.url).path
        if path == '/':
            return route.fulfill(body=markup, content_type='text/html')
        if path.startswith('/static/'):
            return route.fulfill(body=(root / path.lstrip('/')).read_bytes(),
                                 content_type=mimetypes.guess_type(path)[0] or 'text/plain')
        if path == '/api/jobs':
            return route.fulfill(json=[job])
        nonlocal task, network_failure
        if path.endswith('/export/html/ai/start'):
            starts.append(1)
            task = dict(status="running", stage="waiting_ai", task_id=f"task_{len(starts)}",
                        chunk_count=5, completed_chunks=1, current_chunk=2,
                        elapsed_seconds=45, waiting_seconds=8, timeout_seconds=90, last_update_seconds=8)
            return route.fulfill(status=202, json=task)
        if path.endswith('/export/html/ai/progress'):
            if network_failure:
                network_failure = False
                return route.fulfill(status=503, json={"detail": "temporary"})
            return route.fulfill(json=task)
        if path.endswith('/export/html/ai/cancel'):
            task = dict(task, status="cancelling")
            return route.fulfill(json=task)
        if path.endswith('/export/html/status'):
            return route.fulfill(json={'source_revision': 1, 'variants': ['basic', 'ai']})
        if path.endswith('/export/html/basic') or path.endswith('/export/html/ai'):
            label = 'BASIC' if path.endswith('/basic') else 'AI'
            return route.fulfill(body=f'<html><body><p>{label} preview</p></body></html>', content_type='text/html')
        if path.endswith('/export/epub/status'):
            return route.fulfill(json={})
        if path.endswith('/status') and '/jobs/' in path:
            return route.fulfill(json=job)
        if path.endswith('/data'):
            return route.fulfill(json={'reference_image': {'url': ''},
                                      'final_text': 'ข้อความ', 'raw_text': 'ข้อความ', 'revision': 1})
        return route.fulfill(json={'status': 'connected'})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.add_init_script('window.__alerts = []; window.alert = text => window.__alerts.push(text);')
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/*', route_request)
        page.goto('http://127.0.0.1:8000/')
        page.locator('[data-main-tab="history"]').click()
        page.locator('[data-history-open]').click()
        page.locator('[data-main-tab="html"]').click()
        page.wait_for_function("document.querySelector('.CodeMirror').CodeMirror.getValue().includes('AI preview')")
        page.locator('#btn-generate-html-ai').click()
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ชุด 2/5')
        assert page.locator('#html-ai-progress-bar').get_attribute('value') == '1'
        expect(page.locator('#html-ai-progress-detail')).to_contain_text('timeout 90')
        expect(page.locator('#btn-generate-html-ai')).to_be_disabled()
        page.screenshot(path=str(root / 'tests/artifacts/html-ai-progress.png'), full_page=True)
        page.reload()
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ชุด 2/5')
        assert len(starts) == 1, 'Reload must resume polling, never start a duplicate task'
        page.set_viewport_size({'width': 390, 'height': 844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(root / 'tests/artifacts/html-ai-progress-mobile.png'), full_page=True)
        network_failure = True
        expect(page.locator('#html-ai-progress-detail')).to_contain_text('กำลังลองเชื่อมต่อสถานะใหม่', timeout=6000)
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ชุด 2/5')
        page.locator('#btn-cancel-html-ai').click()
        expect(page.locator('#html-ai-progress-title')).to_contain_text('กำลังยกเลิก')
        expect(page.locator('#btn-cancel-html-ai')).to_be_disabled()
        task = dict(task, status='cancelled', stage='cancelled')
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ยกเลิกการสร้าง', timeout=6000)
        expect(page.locator('#btn-retry-html-ai')).to_be_visible()
        page.locator('#btn-retry-html-ai').click()
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ชุด 2/5')
        task = dict(task, status='failed', stage='failed', error='Context size exceeded',
                    meta={'failed_chunk': 2})
        expect(page.locator('#html-ai-progress-error')).to_contain_text('Context size exceeded', timeout=6000)
        expect(page.locator('#html-ai-progress-error')).to_contain_text('2/5')
        page.wait_for_function("document.querySelector('.CodeMirror').CodeMirror.getValue().includes('BASIC preview')")
        expect(page.locator('#btn-generate-html-ai')).to_be_enabled()
        page.locator('#btn-retry-html-ai').click()
        expect(page.locator('#html-ai-progress-title')).to_contain_text('ชุด 2/5')
        task = dict(task, status='completed', stage='completed', completed_chunks=5, error=None)
        expect(page.locator('#html-ai-progress-title')).to_contain_text('สร้าง HTML สำเร็จ', timeout=6000)
        page.wait_for_function("document.querySelector('.CodeMirror').CodeMirror.getValue().includes('AI preview')")
        expect(page.locator('#btn-generate-html-ai')).to_be_enabled()
        assert page.evaluate('window.__alerts') == []
        assert page.evaluate('sessionStorage.getItem("htmlAiJobId")') is None
        assert not errors, errors
        browser.close()
    print('PASS: real progress counts, elapsed/timeout, mobile layout, reload without duplicate work, reconnect, cancel, retry, failure detail and success preview')


if __name__ == '__main__':
    main()
