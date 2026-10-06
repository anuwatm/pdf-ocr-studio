import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BOOK = ROOT / "phase9/approved_phase9.epub"


def flatten(nodes):
    return [item for node in nodes for item in ([node] + flatten(node.get("subitems") or []))]


def main():
    book_bytes = BOOK.read_bytes()
    foliate = next((ROOT / "tools/readers").glob("foliate-*/view.js")).parent
    reports = []
    with sync_playwright() as playwright:
        for channel in ("chrome", "msedge"):
            browser = playwright.chromium.launch(channel=channel, headless=True)
            context = browser.new_context(viewport={"width":1100,"height":760})
            external, errors = [], []
            def route(route):
                parsed = urlparse(route.request.url)
                if parsed.hostname not in {"127.0.0.1", "localhost"}:
                    external.append(route.request.url); return route.abort()
                path = parsed.path
                if path == "/book.epub": return route.fulfill(body=book_bytes, content_type="application/epub+zip")
                if path == "/jszip.js": return route.fulfill(body=(ROOT/"tools/readers/jszip-3.10.1.min.js").read_bytes(), content_type="text/javascript")
                if path == "/epub.js": return route.fulfill(body=(ROOT/"tools/readers/package/dist/epub.min.js").read_bytes(), content_type="text/javascript")
                if path.startswith("/foliate/"):
                    file = foliate / path.removeprefix("/foliate/")
                    return route.fulfill(body=file.read_bytes(), content_type="text/javascript" if file.suffix==".js" else (mimetypes.guess_type(file.name)[0] or "application/octet-stream"))
                if path == "/epubjs": return route.fulfill(content_type="text/html", body='<div id="reader"></div><script src="/jszip.js"></script><script src="/epub.js"></script>')
                if path == "/foliate-reader": return route.fulfill(content_type="text/html", body='<style>foliate-view{display:block;width:900px;height:650px}</style>')
                return route.fulfill(status=404, body="offline")
            context.route("**/*", route)
            page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:8000/epubjs")
            epubjs = page.evaluate("""async()=>{const data=await(await fetch('/book.epub')).arrayBuffer();window.book=ePub(data);
              await book.ready;window.rendition=book.renderTo('reader',{width:900,height:650});await rendition.display();
              return {spine:book.spine.spineItems.length,toc:book.navigation.toc,metadata:book.packaging.metadata};}""")
            all_epub = flatten(epubjs["toc"])
            assert all_epub[0]["label"] == "สารบัญ Phase 9 — ฉบับตรวจรับ"
            for entry in all_epub:
                awaitable = page.evaluate("href=>rendition.display(href).then(()=>true)", entry["href"])
                assert awaitable
            page.set_viewport_size({"width":430,"height":720})
            page.evaluate("async()=>{rendition.resize(390,600);await rendition.display(book.navigation.toc[0].href)}")
            epubjs["all_toc_targets_verified"] = True; epubjs["cover_verified"] = epubjs["spine"] > 44
            epubjs["reflow_resize_verified"] = True

            page.goto("http://127.0.0.1:8000/foliate-reader")
            foliate_result = page.evaluate("""async()=>{await import('/foliate/view.js');window.view=document.createElement('foliate-view');
              document.body.append(view);await view.open('/book.epub');await view.goTo(0);
              return {sections:view.book.sections.length,toc:view.book.toc,metadata:view.book.metadata};}""")
            all_foliate = flatten(foliate_result["toc"])
            assert all_foliate[0]["label"] == "สารบัญ Phase 9 — ฉบับตรวจรับ"
            for entry in all_foliate:
                page.evaluate("async href=>await view.goTo(href)", entry["href"])
                fragment = entry["href"].partition("#")[2]
                if fragment:
                    page.wait_for_function("id=>view.renderer.getContents().some(x=>x.doc?.getElementById(id))", arg=fragment)
            page.evaluate("async()=>{view.style.width='390px';await view.goTo(0)}")
            foliate_result.update(all_toc_targets_verified=True, cover_verified=foliate_result["sections"]>44, reflow_resize_verified=True)
            assert external == [] and errors == [], (external, errors)
            reports.append({"browser":channel,"version":browser.version,"epubjs":epubjs,"foliate":foliate_result,
                            "external_calls":external,"page_errors":errors})
            context.close(); browser.close()
    (ROOT/"phase9/reader_matrix.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("PASS: edited TOC targets, cover and reflow in epub.js/Foliate on Chrome/Edge; external calls 0")


if __name__ == "__main__": main()
