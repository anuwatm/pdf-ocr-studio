"""Chrome/Edge EPUB UI and two independent local reader engines.

Real EPUB API runs against an isolated retained DB; OCR history is stubbed.
Reader libraries stay under tools/, never included in the product frontend.
"""
import base64
import io
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from src.database import JobDatabase
from src.server import app
from src.epub_exporter import prepare_epub_preview, build_epub

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'tests/artifacts/phase8_browser'
SOURCE = '<html><body><h1>บทภาษาไทย</h1><h2>หัวข้อแรก</h2><h3>หัวข้อย่อย</h3><p>น้ำ กำลัง English &amp; ทดสอบ reflow</p><h1>บทสอง</h1><p>ข้อความบทสอง</p></body></html>'

def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    db = JobDatabase(str(ARTIFACTS / 'jobs.db'))
    reports = []
    foliate = next((ROOT / 'tools/readers').glob('foliate-*/view.js')).parent
    reference = 'reader_reference'
    reference_export = ARTIFACTS / reference / 'export'
    reference_export.mkdir(parents=True, exist_ok=True)
    (reference_export / 'basic.html').write_text(SOURCE, encoding='utf-8')
    image = io.BytesIO()
    Image.new('RGB', (160, 240), 'navy').save(image, 'PNG')
    cover = {'data_base64':base64.b64encode(image.getvalue()).decode(), 'alt':'ปกหนังสือภาษาไทย'}
    meta = prepare_epub_preview(reference, source_variant='basic', metadata={'title':'หนังสือทดสอบไทย'}, cover=cover, files_dir=str(ARTIFACTS))
    build_epub(reference,meta['preview_revision'],files_dir=str(ARTIFACTS))
    reference_bytes = (reference_export / 'epub/book.epub').read_bytes()
    (ROOT / 'phase8/reader_fixture.epub').write_bytes(reference_bytes)
    (ARTIFACTS / 'cover.png').write_bytes(image.getvalue())
    with patch('src.server.db',db), patch('src.server.DEFAULT_OUTPUT_DIR',str(ARTIFACTS)), sync_playwright() as pw:
        client = TestClient(app)
        markup = client.get('/').text
        for channel in ('chrome','msedge'):
            job_id = 'browser_'+channel
            if not db.get_job_status(job_id):
                db.create_job(job_id=job_id,filename='หนังสือ.pdf',file_path='fixture.pdf',file_size_bytes=12,total_pages=2,enable_ai=False)
            export = ARTIFACTS / job_id / 'export'
            export.mkdir(parents=True, exist_ok=True)
            (export / 'basic.html').write_text(SOURCE,encoding='utf-8')
            job = dict(job_id=job_id,filename='หนังสือ.pdf',total_pages=2,completed_pages=2,failed_pages=0,status='completed',
                       current_attempt=1,file_size_bytes=12,updated_at='2026-10-04T10:00:00',pages=[dict(page_id=1,page_num=1,status='completed')])
            requests, external, errors = [], [], []
            browser = pw.chromium.launch(channel=channel,headless=True)
            context = browser.new_context(accept_downloads=True)
            def route_request(route):
                url = urlparse(route.request.url)
                path = url.path
                if url.hostname not in {'127.0.0.1','localhost'}:
                    external.append(route.request.url)
                    return route.abort()
                requests.append({'method':route.request.method,'url':route.request.url})
                if path == '/':
                    return route.fulfill(body=markup,content_type='text/html')
                if path.startswith('/static/'):
                    return route.fulfill(body=(ROOT/path.lstrip('/')).read_bytes(),content_type=mimetypes.guess_type(path)[0] or 'text/plain')
                if '/export/epub' in path:
                    response = client.request(route.request.method,path,content=route.request.post_data,
                                              headers={'Content-Type':'application/json'})
                    return route.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
                if path == '/api/jobs':
                    return route.fulfill(json=[job])
                if path.endswith('/export/html/status'):
                    return route.fulfill(json={'variants':[]})
                if path.endswith('/export/html/ai/progress'):
                    return route.fulfill(json={'status':'idle'})
                if path.endswith('/status') and '/jobs/' in path:
                    return route.fulfill(json=job)
                if path.endswith('/data'):
                    return route.fulfill(json={'reference_image':{'url':''},'raw_text':'ไทย','final_text':'ไทย','revision':1})
                if path == '/reader/book.epub':
                    return route.fulfill(body=reference_bytes,content_type='application/epub+zip')
                if path.startswith('/reader/foliate/'):
                    file = foliate / path.removeprefix('/reader/foliate/')
                    ctype = 'text/javascript' if file.suffix == '.js' else (mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                    return route.fulfill(body=file.read_bytes(), content_type=ctype)
                if path == '/reader/jszip.js':
                    return route.fulfill(body=(ROOT/'tools/readers/jszip-3.10.1.min.js').read_bytes(),content_type='text/javascript')
                if path == '/reader/epub.js':
                    return route.fulfill(body=(ROOT/'tools/readers/package/dist/epub.min.js').read_bytes(),content_type='text/javascript')
                if path == '/reader/epubjs':
                    return route.fulfill(content_type='text/html',body='<html><body><div id="reader" style="width:800px;height:650px"></div><script src="/reader/jszip.js"></script><script src="/reader/epub.js"></script></body></html>')
                if path == '/reader/foliate':
                    return route.fulfill(content_type='text/html',body='<html><body><style>foliate-view {display:block;width:800px;height:650px}</style></body></html>')
                return route.fulfill(json={'status':'offline'})
            context.route('**/*',route_request)
            page = context.new_page()
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.add_init_script('window.__alerts=[];window.alert=text=>window.__alerts.push(text)')
            page.goto('http://127.0.0.1:8000/')
            page.locator('[data-main-tab="history"]').click()
            page.locator('[data-history-open]').click()
            page.locator('[data-main-tab="epub"]').click()
            page.locator('#epub-title').fill('หนังสือภาษาไทย')
            page.locator('#epub-cover').set_input_files(str(ARTIFACTS/'cover.png'))
            page.locator('#epub-cover-alt').fill('ปกหนังสือไทย')
            page.locator('#btn-generate-epub-preview').click()
            expect(page.locator('#btn-build-epub')).to_be_enabled()
            expect(page.locator('#epub-preview-details')).to_contain_text('revision')
            frame = page.frame_locator('#epub-preview-frame')
            expect(frame.locator('img')).to_have_attribute('alt','ปกหนังสือไทย')
            frame.locator('nav a',has_text='หัวข้อย่อย').click()
            expect(frame.locator('h3')).to_contain_text('หัวข้อย่อย')
            page.locator('#btn-epub-subtab-source').click()
            expect(page.locator('#epub-source-editor')).to_contain_text('')
            assert 'ภาษาไทย' in page.locator('#epub-source-editor').input_value()
            page.locator('#btn-epub-subtab-preview').click()
            with page.expect_download() as downloading:
                page.locator('#btn-build-epub').click()
            download = downloading.value
            assert download.suggested_filename.endswith('.epub')
            download.save_as(str(ARTIFACTS/(channel+'.epub')))
            page.locator('#epub-title').fill('ปรับชื่อ')
            expect(page.locator('#btn-build-epub')).to_be_disabled()
            page.locator('#btn-generate-epub-preview').click()
            expect(page.locator('#btn-build-epub')).to_be_enabled()
            with page.expect_download():
                page.locator('#btn-build-epub').click()
            # Source changes after preview: API must reject package and stale download.
            (export/'basic.html').write_text(SOURCE.replace('บทสอง','บทเปลี่ยน'),encoding='utf-8')
            page.locator('#btn-build-epub').click()
            page.wait_for_function('window.__alerts.some(x=>x.includes("Conflict:"))')
            assert client.get(f'/api/jobs/{job_id}/export/epub/download').status_code == 409
            (export/'basic.html').write_text('<html><body><h1>หนึ่ง</h1><h3>ข้ามระดับ</h3></body></html>',encoding='utf-8')
            page.locator('#btn-generate-epub-preview').click()
            page.wait_for_function('window.__alerts.some(x=>x.includes("Heading hierarchy"))')
            (export/'basic.html').write_text(SOURCE,encoding='utf-8')
            page.locator('#btn-generate-epub-preview').click()
            expect(page.locator('#btn-build-epub')).to_be_enabled()
            page.screenshot(path=str(ROOT/f'phase8/{channel}-epub-studio.png'),full_page=True)
            # External readers load actual EPUB bytes locally, independently from product preview.
            page.goto('http://127.0.0.1:8000/reader/epubjs')
            epubjs = page.evaluate('''async () => {
                const data=await (await fetch('/reader/book.epub')).arrayBuffer();
                window.book=ePub(data); await book.ready;
                window.rendition=book.renderTo('reader',{width:800,height:650});
                await rendition.display();
                return {toc:book.navigation.toc, spine:book.spine.spineItems.length, metadata:book.packaging.metadata};
            }''')
            assert epubjs['spine'] == 3
            assert epubjs['toc'][0]['label'] == 'บทภาษาไทย'
            expect(page.frame_locator('iframe').locator('img')).to_have_attribute('alt','ปกหนังสือภาษาไทย')
            assert page.frame_locator('iframe').locator('img').evaluate('(img)=>img.complete && img.naturalWidth>0')
            page.evaluate('async () => await rendition.display(book.navigation.toc[0].href)')
            expect(page.frame_locator('iframe').locator('body')).to_contain_text('น้ำ กำลัง')
            epubjs['render_checks'] = page.frame_locator('iframe').locator('p').evaluate('(p)=>({font:getComputedStyle(p).fontFamily,lineHeight:getComputedStyle(p).lineHeight,whiteSpace:getComputedStyle(p).whiteSpace})')
            assert 'Leelawadee' in epubjs['render_checks']['font']
            def flatten(entries):
                result = []
                for entry in entries:
                    result.append(entry)
                    result.extend(flatten(entry.get('subitems') or []))
                return result
            for entry in flatten(epubjs['toc']):
                page.evaluate('async href => await rendition.display(href)',entry['href'])
                expect(page.frame_locator('iframe').locator('body')).to_contain_text(entry['label'])
            epubjs['all_toc_targets_verified'] = True
            page.set_viewport_size({'width':480,'height':760})
            page.evaluate('async()=>{rendition.resize(420,600);await rendition.display(book.navigation.toc[0].href)}')
            expect(page.frame_locator('iframe').locator('p')).to_contain_text('น้ำ กำลัง')
            epubjs['reflow_resize_verified'] = True
            page.set_viewport_size({'width':1280,'height':720})
            page.screenshot(path=str(ROOT/f'phase8/{channel}-epubjs.png'))
            page.goto('http://127.0.0.1:8000/reader/foliate')
            foliate_result = page.evaluate('''async () => {
                await import('/reader/foliate/view.js');
                window.view=document.createElement('foliate-view');document.body.append(view);
                await view.open('/reader/book.epub'); await view.goTo(1);
                return {toc:view.book.toc, sections:view.book.sections.length, metadata:view.book.metadata};
            }''')
            assert foliate_result['sections'] == 3
            page.wait_for_function("view.renderer.getContents().some(x=>x.doc?.body.textContent.includes('น้ำ กำลัง'))")
            foliate_result['render_checks'] = page.evaluate('''()=>{const p=view.renderer.getContents()[0].doc.querySelector('p');return {font:p.ownerDocument.defaultView.getComputedStyle(p).fontFamily}}''')
            assert 'Leelawadee' in foliate_result['render_checks']['font']
            for entry in flatten(foliate_result['toc']):
                page.evaluate('async href=>await view.goTo(href)',entry['href'])
                page.wait_for_function('(label)=>view.renderer.getContents().some(x=>x.doc?.body.textContent.includes(label))',arg=entry['label'])
            foliate_result['all_toc_targets_verified'] = True
            page.evaluate('async()=>await view.goTo(0)')
            page.wait_for_function('view.renderer.getContents().some(x=>{const img=x.doc?.querySelector("img");return img?.complete && img.naturalWidth>0})')
            foliate_result['cover_verified'] = True
            page.evaluate('async()=>{view.style.width="420px";await view.goTo(1)}')
            page.wait_for_function("view.renderer.getContents().some(x=>x.doc?.body.textContent.includes('น้ำ กำลัง'))")
            foliate_result['reflow_resize_verified'] = True
            page.screenshot(path=str(ROOT/f'phase8/{channel}-foliate.png'))
            assert external == [], external
            assert errors == [], errors
            report = dict(browser=channel,version=browser.version,external_calls=external,page_errors=errors,
                          requests=requests,epubjs=epubjs,foliate=foliate_result,
                          coverage=['cover','nested TOC','source view','preview','automatic download','dirty config','stale/409','invalid heading','regenerate','offline AI'])
            reports.append(report)
            context.close()
            browser.close()
    (ROOT/'phase8/browser_network_log.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: Chrome/Edge UI and epub.js/Foliate reader engines; external calls = 0')

if __name__ == '__main__':
    main()
