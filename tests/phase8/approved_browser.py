"""Browser and external-reader audit on approved demo-derived data only."""
import base64
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from src.database import JobDatabase
from src.job_models import JobStatus
from src.server import app
from src.epub_exporter import prepare_epub_preview, build_epub

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'tests/artifacts/phase8_approved_browser'

def main():
    ART.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'tests/artifacts/approved_44pages_job/export/basic.html').read_bytes()
    db=JobDatabase(str(ART/'jobs.db'))
    cover={'data_base64':base64.b64encode((ROOT/'demo/01.png').read_bytes()).decode(),'alt':'เอกสาร demo/01.png ใช้ทดสอบรูปปก'}
    job='approved_epub_44'
    export=ART/job/'export'
    export.mkdir(parents=True,exist_ok=True)
    (export/'basic.html').write_bytes(source)
    if not db.get_job_status(job):
        db.create_job(job_id=job,filename='approved-demo-44.pdf',file_path=str(ROOT/'demo/01.pdf'),file_size_bytes=len(source),total_pages=44,enable_ai=False)
    db.update_job_status(job,JobStatus.COMPLETED)
    meta=prepare_epub_preview(job,source_variant='basic',chapter_split='page',cover=cover,files_dir=str(ART))
    build_epub(job,meta['preview_revision'],files_dir=str(ART))
    book=(export/'epub/book.epub').read_bytes()
    (ROOT/'phase8/approved_reader_fixture.epub').write_bytes(book)
    foliate=next((ROOT/'tools/readers').glob('foliate-*/view.js')).parent
    reports=[]
    with patch('src.server.db',db),patch('src.server.DEFAULT_OUTPUT_DIR',str(ART)),sync_playwright() as pw:
        client=TestClient(app)
        for channel in ('chrome','msedge'):
            browser=pw.chromium.launch(channel=channel,headless=True)
            context=browser.new_context(accept_downloads=True)
            requests,external,errors=[],[],[]
            def route_request(route):
                url=urlparse(route.request.url)
                path=url.path
                if url.hostname not in {'127.0.0.1','localhost'}:
                    external.append(route.request.url)
                    return route.abort()
                requests.append({'method':route.request.method,'url':route.request.url})
                if path=='/reader/book.epub': return route.fulfill(body=book,content_type='application/epub+zip')
                if path=='/reader/epubjs': return route.fulfill(content_type='text/html',body='<div id="reader" style="width:800px;height:650px"></div><script src="/reader/jszip.js"></script><script src="/reader/epub.js"></script>')
                if path=='/reader/foliate': return route.fulfill(content_type='text/html',body='<style>foliate-view{display:block;width:800px;height:650px}</style>')
                if path=='/reader/jszip.js': return route.fulfill(body=(ROOT/'tools/readers/jszip-3.10.1.min.js').read_bytes(),content_type='text/javascript')
                if path=='/reader/epub.js': return route.fulfill(body=(ROOT/'tools/readers/package/dist/epub.min.js').read_bytes(),content_type='text/javascript')
                if path.startswith('/reader/foliate/'):
                    file=foliate/path.removeprefix('/reader/foliate/')
                    ctype = 'text/javascript' if file.suffix == '.js' else (mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                    return route.fulfill(body=file.read_bytes(),content_type=ctype)
                response=client.request(route.request.method,path,content=route.request.post_data,headers={'Content-Type':'application/json'})
                return route.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
            context.route('**/*',route_request)
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:8000/')
            page.locator('[data-main-tab="history"]').click()
            page.locator('[data-history-open]').click()
            page.locator('[data-main-tab="epub"]').click()
            expect(page.locator('#epub-preview-details')).to_contain_text('44 บท')
            page.frame_locator('#epub-preview-frame').locator('nav a').first.click()
            expect(page.frame_locator('#epub-preview-frame').locator('.chapter').first).to_be_visible()
            page.locator('#btn-epub-subtab-source').click()
            assert 'ภาษา' in page.locator('#epub-source-editor').input_value()
            page.locator('#btn-epub-subtab-preview').click()
            with page.expect_download() as download:
                page.locator('#btn-build-epub').click()
            assert download.value.suggested_filename.endswith('.epub')
            download.value.save_as(str(ART/(channel+'.epub')))
            page.screenshot(path=str(ROOT/f'phase8/{channel}-approved-studio.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'), 'Mobile page overflows'
            page.locator('#btn-generate-epub-preview').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#btn-build-epub')).to_be_enabled()
            assert client.get(f'/api/jobs/{job}/export/epub/status').json()['cover'], 'Existing cover must survive regeneration'
            assert page.locator('#epub-preview-frame').get_attribute('sandbox') == ''
            assert page.locator('#epub-preview-frame').get_attribute('title')
            page.set_viewport_size({'width':1280,'height':720})
            page.goto('http://127.0.0.1:8000/reader/epubjs')
            epubjs=page.evaluate('''async()=>{
                const bytes=await(await fetch('/reader/book.epub')).arrayBuffer();
                window.book=ePub(bytes);await book.ready;window.rendition=book.renderTo('reader',{width:800,height:650});
                await rendition.display();return {toc:book.navigation.toc,spine:book.spine.spineItems.length,metadata:book.packaging.metadata};
            }''')
            assert epubjs['spine']==45
            expect(page.frame_locator('iframe').locator('img')).to_have_attribute('alt',cover['alt'])
            page.wait_for_function('rendition.getContents().some(c=>{const img=c.document.querySelector("img");return img?.complete&&img.naturalWidth>0})')
            def flatten(entries):
                values=[]
                for entry in entries:
                    values.append(entry)
                    values.extend(flatten(entry.get('subitems') or []))
                return values
            for entry in flatten(epubjs['toc']):
                page.evaluate('async href=>await rendition.display(href)',entry['href'])
                fragment=entry['href'].partition('#')[2]
                if fragment:
                    page.wait_for_function('(id)=>rendition.getContents().some(c=>c.document.getElementById(id))',arg=fragment)
            page.evaluate('async()=>{rendition.resize(420,600);await rendition.display(book.navigation.toc[1].href)}')
            epubjs['render']=page.evaluate('()=>{const p=rendition.getContents()[0].document.querySelector("p");return {font:getComputedStyle(p).fontFamily,text:p.textContent}}')
            assert 'Leelawadee' in epubjs['render']['font']
            epubjs['all_toc_targets_verified']=True
            epubjs['cover_verified']=True
            epubjs['reflow_resize_verified']=True
            page.screenshot(path=str(ROOT/f'phase8/{channel}-approved-epubjs.png'))
            page.goto('http://127.0.0.1:8000/reader/foliate')
            foliate_report=page.evaluate('''async()=>{
                await import('/reader/foliate/view.js');window.view=document.createElement('foliate-view');document.body.append(view);
                await view.open('/reader/book.epub');await view.goTo(0);return {toc:view.book.toc,sections:view.book.sections.length,metadata:view.book.metadata};
            }''')
            assert foliate_report['sections']==45
            page.wait_for_function('view.renderer.getContents().some(x=>{const img=x.doc?.querySelector("img");return img?.complete&&img.naturalWidth>0})')
            for entry in flatten(foliate_report['toc']):
                page.evaluate('async href=>await view.goTo(href)',entry['href'])
                fragment=entry['href'].partition('#')[2]
                if fragment:
                    page.wait_for_function('(id)=>view.renderer.getContents().some(x=>x.doc?.getElementById(id))',arg=fragment)
            page.evaluate('async()=>{view.style.width="420px";await view.goTo(1)}')
            foliate_report['render']=page.evaluate('()=>{const doc=view.renderer.getContents()[0].doc;const p=doc.querySelector("p");return {font:doc.defaultView.getComputedStyle(p).fontFamily,text:p.textContent}}')
            assert 'Leelawadee' in foliate_report['render']['font']
            foliate_report.update(all_toc_targets_verified=True,cover_verified=True,reflow_resize_verified=True)
            page.screenshot(path=str(ROOT/f'phase8/{channel}-approved-foliate.png'))
            assert not external,external
            assert not errors,errors
            reports.append({'browser':channel,'version':browser.version,'external_calls':external,'page_errors':errors,
                            'requests':requests,'epubjs':epubjs,'foliate':foliate_report,'scope':'approved demo 44 pages; PNG cover from demo/01.png'})
            context.close()
            browser.close()
    (ROOT/'phase8/approved_browser_network_log.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: approved 44 pages, Chrome/Edge UI and EPUB.js/Foliate renderers, all TOC targets, cover, CSS and resize; external calls 0')

if __name__=='__main__': main()
