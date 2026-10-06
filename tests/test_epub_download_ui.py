"""EPUB creation downloads automatically; mocked APIs never modify real jobs."""
import io
import mimetypes
import zipfile
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
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as package:
        package.writestr('mimetype', 'application/epub+zip')
    preview_ready = False
    package_ready = False
    fail_build = False
    fail_download = False
    calls, errors, downloads = [], [], []

    def route_request(route):
        nonlocal preview_ready, package_ready
        path = urlparse(route.request.url).path
        if path == '/':
            return route.fulfill(body=markup, content_type='text/html')
        if path.startswith('/static/'):
            return route.fulfill(body=(root / path.lstrip('/')).read_bytes(),
                                 content_type=mimetypes.guess_type(path)[0] or 'text/plain')
        if path == '/api/jobs':
            return route.fulfill(json=[job])
        if path.endswith('/export/epub/status'):
            if package_ready:
                # Package success must still download if refreshing status fails.
                return route.fulfill(status=503, json={'detail': 'temporary failure'})
            return route.fulfill(json={'preview_ready': preview_ready, 'epub_ready': False,
                                       'preview_revision': 'rev1', 'chapters_count': 1})
        if path.endswith('/export/epub/preview'):
            if route.request.method == 'POST':
                preview_ready = True
                return route.fulfill(json={'meta': {'preview_revision': 'rev1'}})
            return route.fulfill(body='<html><body>Preview</body></html>', content_type='application/xhtml+xml')
        if path.endswith('/export/epub'):
            calls.append(route.request.post_data_json)
            if fail_build:
                return route.fulfill(status=409, json={'detail': 'Conflict: source HTML changed'})
            package_ready = True
            return route.fulfill(json={'status': 'ready', 'meta': {'epub_ready': True}})
        if path.endswith('/export/epub/download'):
            if fail_download:
                return route.fulfill(status=404, json={'detail': 'EPUB not generated'})
            return route.fulfill(body=buffer.getvalue(), content_type='application/epub+zip',
                                 headers={'Content-Disposition': 'attachment; filename="example.epub"'})
        if path.endswith('/export/html/status'):
            return route.fulfill(json={'variants': []})
        if path.endswith('/export/html/ai/progress'):
            return route.fulfill(json={'status': 'idle'})
        if path.endswith('/status') and '/jobs/' in path:
            return route.fulfill(json=job)
        if path.endswith('/data'):
            return route.fulfill(json={'reference_image': {'url': ''}, 'final_text': 'ข้อความ',
                                       'raw_text': 'ข้อความ', 'revision': 1})
        return route.fulfill(json={'status': 'offline'})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(accept_downloads=True)
        context.route('**/*', route_request)
        page = context.new_page()
        page.add_init_script('window.__alerts = []; window.alert = text => window.__alerts.push(text);')
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('download', lambda download: downloads.append(download))
        page.goto('http://127.0.0.1:8000/')
        page.locator('[data-main-tab="history"]').click()
        page.locator('[data-history-open]').click()
        page.locator('[data-main-tab="epub"]').click()
        expect(page.locator('#btn-build-epub')).to_be_disabled()
        page.locator('#btn-generate-epub-preview').click()
        expect(page.locator('#btn-build-epub')).to_be_enabled()
        with page.expect_download() as pending:
            page.locator('#btn-build-epub').click()
        download = pending.value
        assert download.suggested_filename == 'example.epub', (download.suggested_filename, download.url)
        assert download.failure() is None
        assert calls == [{'base_preview_revision': 'rev1'}]
        expect(page.locator('#epub-export-status-badge')).to_contain_text('เริ่มดาวน์โหลด')
        expect(page.locator('#btn-dl-epub')).to_be_visible()
        expect(page.locator('#btn-download-epub')).to_be_visible()
        fail_build = True
        page.locator('#btn-build-epub').click()
        expect(page.locator('#btn-build-epub')).to_be_enabled()
        assert len(downloads) == 1, 'Failed creation must never trigger a download'
        assert 'Conflict: source HTML changed' in page.evaluate('window.__alerts')[0]
        fail_build = False
        fail_download = True
        page.locator('#btn-build-epub').click()
        expect(page.locator('#btn-build-epub')).to_be_enabled()
        assert len(downloads) == 1, 'An API error must never be saved as an EPUB or JSON download'
        assert 'HTTP 404' in page.evaluate('window.__alerts')[1]
        assert not errors, errors
        browser.close()
    print('PASS: preview required; creation downloads .epub; manual download remains; status refresh failure does not block download; failed creation never downloads')


if __name__ == '__main__':
    main()
