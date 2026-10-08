"""Phase 8 EPUB export with XHTML Quick Preview.

The preview and the final EPUB are produced from the same canonical XHTML
payload.  Packaging never calls a Local LLM and never mutates Phase 7 files.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import posixpath
import re
import zipfile
import base64
from functools import wraps
import inspect
from PIL import Image
from src.job_artifact_guard import guard_artifacts
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit

from src.file_utils import atomic_write_bytes, atomic_write_json, atomic_write_text


EPUB_SCHEMA_VERSION = "9.0"
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 1000
ALLOWED_SOURCE_VARIANTS = {"auto", "basic", "ai", "final", "structured"}
ALLOWED_CHAPTER_SPLITS = {"heading", "page"}
BLOCK_TAGS = {"p", "h1", "h2", "h3", "table"}
TABLE_TAGS = {"thead", "tbody", "tfoot", "tr", "th", "td", "caption"}
INLINE_TAGS = {"b", "i", "strong", "em", "u", "s", "span", "a"}
DISCARD_CONTENT_TAGS = {
    "head", "script", "style", "iframe", "object", "svg", "math",
    "form", "button", "textarea", "select", "template",
}

BOOK_CSS = """body {
  font-family: 'Leelawadee UI', Tahoma, Arial, sans-serif;
  line-height: 1.65;
  margin: 5%;
  color: #202124;
  background: #fff;
}
h1, h2, h3 { line-height: 1.3; margin: 1.4em 0 0.55em; }
h1 { font-size: 1.8em; }
h2 { font-size: 1.45em; }
h3 { font-size: 1.2em; }
p { margin: 0 0 0.9em; text-align: justify; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #888; padding: 0.35em; vertical-align: top; }
th { font-weight: 700; background: #eee; }
.pre-wrap { white-space: pre-wrap; }
.page-marker { color: #666; font-style: italic; }
img { max-width: 100%; height: auto; }
nav[epub\\:type='toc'] ol { padding-left: 1.5em; }
nav[epub\\:type='toc'] li { margin: 0.35em 0; }
"""

PREVIEW_CSS = BOOK_CSS + """
body { max-width: 860px; margin: 0 auto; padding: 2rem; }
.preview-note { padding: 0.8rem 1rem; background: #eef4ff; border-left: 4px solid #4c6ef5; }
.chapter { border-top: 1px solid #ddd; padding-top: 1rem; margin-top: 2rem; }
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_job_dir(files_dir: str, job_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id or ""):
        raise ValueError("Invalid job id")
    base = os.path.realpath(files_dir)
    target = os.path.realpath(os.path.join(base, job_id))
    try:
        if os.path.commonpath([base, target]) != base or target == base:
            raise ValueError("Invalid job path")
    except ValueError as exc:
        raise ValueError("Invalid job path") from exc
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Job directory not found: {job_id}")
    return target


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_metadata(metadata: Optional[Dict[str, Any]], job_id: str) -> Dict[str, str]:
    raw = metadata if isinstance(metadata, dict) else {}

    def clean(name: str, default: str = "", limit: int = 500) -> str:
        value = str(raw.get(name, default) or default)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()
        return value[:limit]

    language = clean("language", "th", 20).lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", language):
        language = "th"
    title = clean("title", f"OCR Document {job_id}", 300)
    identifier = clean("identifier", "", 200)
    published_date = clean("date", "", 40)
    if published_date:
        try:
            datetime.fromisoformat(published_date.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('Date must use ISO 8601 format') from exc
    return {
        "title": title or f"OCR Document {job_id}",
        "language": language,
        "identifier": identifier,
        "creator": clean("creator", "", 300),
        "publisher": clean("publisher", "", 300),
        "description": clean("description", "", 2000),
        "date": published_date,
    }


def _source_revision(path: str) -> str:
    with open(path, "rb") as stream:
        content = stream.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("HTML source exceeds the 20 MB Phase 8 limit")
    return _hash_bytes(content)[:24]


def _resolve_source(job_dir: str, variant: str) -> Tuple[str, str, str]:
    requested = (variant or "auto").lower().strip()
    if requested not in ALLOWED_SOURCE_VARIANTS:
        raise ValueError("Allowed EPUB source variants: auto, basic, ai, final, structured")

    export_dir = os.path.join(job_dir, "export")
    export_meta = _read_json(os.path.join(export_dir, "export_meta.json"))
    current_final_revision = export_meta.get("current_source_revision")

    candidates: List[str]
    if requested == "auto":
        final_meta = export_meta.get("final", {}) if isinstance(export_meta.get("final"), dict) else {}
        final_is_current = final_meta.get("saved_at") == current_final_revision
        candidates = (["final"] if final_is_current else []) + ["basic", "ai"]
    else:
        candidates = [requested]

    for candidate in candidates:
        path = (os.path.join(export_dir, "structured", "structured.html")
                if candidate == "structured" else os.path.join(export_dir, f"{candidate}.html"))
        if os.path.isfile(path):
            if candidate == "structured":
                from src.structured_layout import get_structured_status
                status = get_structured_status(os.path.basename(job_dir), files_dir=os.path.dirname(job_dir))
                if status.get("is_stale"):
                    raise ValueError("Conflict: structured export is stale. Regenerate structured export.")
            return candidate, path, _source_revision(path)

    if requested == "structured":
        from src.structured_layout import generate_structured_exports
        generate_structured_exports(os.path.basename(job_dir), files_dir=os.path.dirname(job_dir))
        path = os.path.join(export_dir, "structured", "structured.html")
        return "structured", path, _source_revision(path)

    if requested == "auto":
        from src.html_exporter import generate_basic_html

        generate_basic_html(os.path.basename(job_dir), files_dir=os.path.dirname(job_dir))
        basic_path = os.path.join(export_dir, "basic.html")
        return "basic", basic_path, _source_revision(basic_path)

    raise FileNotFoundError(f"HTML source '{requested}.html' not found")


class _Phase7BlockParser(HTMLParser):
    """Extracts semantic blocks and safe inline markup from a Phase 7 document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.discard_depth = 0
        self.page_stack: List[Optional[str]] = []
        self.current: Optional[Dict[str, Any]] = None
        self.blocks: List[Dict[str, Any]] = []
        self.list_depth = 0

    @staticmethod
    def _attrs(attrs: List[Tuple[str, Optional[str]]]) -> Dict[str, str]:
        return {str(k).lower(): str(v or "") for k, v in attrs}

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in DISCARD_CONTENT_TAGS:
            self.discard_depth += 1
            return
        if self.discard_depth:
            return
        if tag == "body":
            self.in_body = True
            return
        if not self.in_body:
            return

        attr_map = self._attrs(attrs)
        if tag in {"ul", "ol"}:
            if self.list_depth == 0:
                self._finish_block()
                self.current = {"tag": tag, "page": self.page_stack[-1] if self.page_stack else None,
                                "class": "", "inner": [], "text": []}
            else:
                self.current["inner"].append(f"<{tag}>")
            self.list_depth += 1
            return
        if self.list_depth and tag in {"li", "p", "h1", "h2", "h3"}:
            self.current["inner"].append(f"<{tag}>")
            return
        if tag == "section":
            self.page_stack.append(attr_map.get("data-page"))
            return
        if self.current is not None and self.current.get("tag") == "table" and tag in TABLE_TAGS:
            span_attrs = []
            for name in ("rowspan", "colspan"):
                value = attr_map.get(name, "")
                if value.isdigit() and 1 <= int(value) <= 1000:
                    span_attrs.append(f' {name}="{int(value)}"')
            self.current["inner"].append(f"<{tag}{''.join(span_attrs)}>")
            return
        if tag in BLOCK_TAGS:
            self._finish_block()
            css_class = attr_map.get("class", "")
            allowed_classes = " ".join(
                part for part in css_class.split() if part in {"pre-wrap", "page-marker"}
            )
            self.current = {
                "tag": tag,
                "page": self.page_stack[-1] if self.page_stack else attr_map.get("data-page"),
                "class": allowed_classes,
                "source_id": attr_map.get("id", "") if tag in {"h1", "h2", "h3"} else "",
                "inner": [],
                "text": [],
            }
            return
        if self.current is None:
            return
        if tag in INLINE_TAGS:
            link_attr = ""
            if tag == "a":
                # Keep link text; no external navigation in offline preview/package.
                pass
            self.current["inner"].append(f"<{tag}{link_attr}>")
        elif tag == "br":
            self.current["inner"].append("<br />")
            self.current["text"].append("\n")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "br" and self.current is not None and not self.discard_depth:
            self.current["inner"].append("<br />")
            self.current["text"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DISCARD_CONTENT_TAGS:
            if self.discard_depth:
                self.discard_depth -= 1
            return
        if self.discard_depth:
            return
        if tag == "body":
            self._finish_block()
            self.in_body = False
            return
        if not self.in_body:
            return
        if tag in {"ul", "ol"} and self.list_depth:
            self.list_depth -= 1
            if self.list_depth:
                self.current["inner"].append(f"</{tag}>")
            else:
                self._finish_block()
            return
        if self.current is not None and self.current.get("tag") == "table" and tag in TABLE_TAGS:
            self.current["inner"].append(f"</{tag}>")
            return
        if self.list_depth and tag in {"li", "p", "h1", "h2", "h3"}:
            self.current["inner"].append(f"</{tag}>")
            self.current["text"].append("\n")
            return
        if tag in BLOCK_TAGS:
            self._finish_block()
        elif tag in INLINE_TAGS and self.current is not None:
            self.current["inner"].append(f"</{tag}>")
        elif tag == "section" and self.page_stack:
            self.page_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.discard_depth or not self.in_body:
            return
        if self.current is None and data.strip():
            self.current = {"tag": "p", "page": self.page_stack[-1] if self.page_stack else None,
                            "class": "", "inner": [], "text": []}
        if self.current is None:
            return
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", data)
        self.current["inner"].append(html.escape(cleaned, quote=False))
        self.current["text"].append(cleaned)

    def close(self) -> None:
        super().close()
        self._finish_block()

    def _finish_block(self) -> None:
        if self.current is None:
            return
        visible = "".join(self.current["text"]).strip()
        if visible:
            self.current["visible_text"] = visible
            self.current["inner_html"] = "".join(self.current["inner"])
            self.blocks.append(self.current)
        self.current = None


def _parse_blocks(source_html: str) -> List[Dict[str, Any]]:
    parser = _Phase7BlockParser()
    parser.feed(source_html)
    parser.close()
    if not parser.blocks:
        raise ValueError("HTML source contains no exportable semantic content")

    heading_signatures: Dict[str, int] = {}
    used_ids = set()
    last_level = 0
    for block in parser.blocks:
        tag = block["tag"]
        if tag.startswith("h"):
            level = int(tag[1])
            if last_level and level - last_level > 1:
                raise ValueError(f"Heading hierarchy jumps from h{last_level} to h{level}")
            last_level = level
            source_id = str(block.pop("source_id", "")).strip()
            valid_source_id = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", source_id))
            if valid_source_id and source_id not in used_ids and not source_id.startswith("chapter-"):
                stable_id = source_id
                block["id_source"] = "html"
            else:
                signature = "\0".join((tag, block.get("visible_text", "").strip().casefold(), str(block.get("page") or "")))
                occurrence = heading_signatures.get(signature, 0) + 1
                heading_signatures[signature] = occurrence
                suffix = "" if occurrence == 1 else f"-{occurrence}"
                stable_id = "heading-" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12] + suffix
                while stable_id in used_ids:
                    occurrence += 1
                    stable_id = "heading-" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12] + f"-{occurrence}"
                block["id_source"] = "generated" if not source_id else "duplicate-remapped"
            block["id"] = stable_id
            used_ids.add(stable_id)
    return parser.blocks


def _split_chapters(
    blocks: List[Dict[str, Any]],
    split_mode: str,
    book_title: str,
) -> List[Dict[str, Any]]:
    mode = (split_mode or "heading").lower().strip()
    if mode not in ALLOWED_CHAPTER_SPLITS:
        raise ValueError("Allowed chapter split modes: heading, page")

    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    has_h1 = any(block["tag"] == "h1" for block in blocks)

    for block in blocks:
        should_split = False
        if current:
            if mode == "heading" and has_h1 and block["tag"] == "h1":
                should_split = True
            elif mode == "page" or (mode == "heading" and not has_h1):
                previous_page = current[-1].get("page")
                should_split = bool(block.get("page") and block.get("page") != previous_page)
        if should_split:
            groups.append(current)
            current = []
        current.append(block)
    if current:
        groups.append(current)

    chapters: List[Dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        first_heading = next((b for b in group if b["tag"] in {"h1", "h2", "h3"}), None)
        page = next((b.get("page") for b in group if b.get("page")), None)
        title = (
            first_heading["visible_text"]
            if first_heading
            else (f"หน้า {page}" if page else (book_title if index == 1 else f"ส่วนที่ {index}"))
        )
        chapters.append({
            "index": index,
            "title": title[:200],
            "filename": f"chapter-{index:03d}.xhtml",
            "blocks": group,
        })
    return chapters


def _render_block(block: Dict[str, Any]) -> str:
    tag = block["tag"]
    attrs: List[str] = []
    if tag.startswith("h") and block.get("id"):
        attrs.append(f'id="{html.escape(block["id"], quote=True)}"')
    if block.get("page"):
        page = re.sub(r"[^0-9A-Za-z_-]", "", str(block["page"]))
        if page:
            attrs.append(f'data-page="{page}"')
    if block.get("class"):
        attrs.append(f'class="{html.escape(block["class"], quote=True)}"')
    attr_text = (" " + " ".join(attrs)) if attrs else ""
    return f"<{tag}{attr_text}>{block['inner_html']}</{tag}>"


def _chapter_xhtml(chapter: Dict[str, Any], metadata: Dict[str, str]) -> str:
    language = html.escape(metadata["language"], quote=True)
    title = html.escape(chapter["title"], quote=False)
    body = "\n".join(_render_block(block) for block in chapter["blocks"])
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../styles/book.css" />
</head>
<body>
  <section class="chapter" epub:type="chapter">
{body}
  </section>
</body>
</html>'''


def _toc_markup(chapters, preview=False):
    def render(nodes):
        return '<ol>' + ''.join('<li><a href="' + html.escape(n['href'], quote=True) + '">' +
            html.escape(n['label']) + '</a>' + (render(n['children']) if n['children'] else '') + '</li>'
            for n in nodes) + '</ol>'
    roots = []
    for chapter in chapters:
        headings = [b for b in chapter['blocks'] if b.get('id')]
        prefix = '' if preview else 'text/' + chapter['filename']
        first = headings[0] if headings else None
        target = ('#chapter-%03d' % chapter['index']) if preview else prefix + ('#' + first['id'] if first else '')
        parent = {'href': target, 'label': chapter['title'], 'children': []}
        roots.append(parent)
        stack = [(int(first['tag'][1]) if first else 0, parent)]
        for heading in headings[1:]:
            level = int(heading['tag'][1])
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            node = {'href': prefix + '#' + heading['id'], 'label': heading['visible_text'], 'children': []}
            stack[-1][1]['children'].append(node)
            stack.append((level, node))
    return render(roots)

def _nav_xhtml(chapters, metadata, cover=None, toc_entries=None, toc_targets=None):
    language = html.escape(metadata['language'], quote=True)
    title = html.escape(metadata['title'])
    if toc_entries is not None and toc_targets is not None:
        from src.toc_editor import render_toc_markup
        toc_markup = render_toc_markup(toc_entries, toc_targets, preview=False)
    else:
        toc_markup = _toc_markup(chapters)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">
<head><meta charset="utf-8" /><title>{title}</title></head>
<body><nav epub:type="toc" id="toc" aria-label="สารบัญ"><h1>สารบัญ</h1>{toc_markup}</nav>
{('<nav epub:type="landmarks" hidden="hidden"><h2>ส่วนประกอบหนังสือ</h2><ol><li><a epub:type="cover" href="text/cover.xhtml">ปกหนังสือ</a></li></ol></nav>') if cover else ''}
</body></html>'''


def _preview_xhtml(chapters: List[Dict[str, Any]], metadata: Dict[str, str], preview_revision: str,
                   job_id="", cover=None, toc_entries=None, toc_targets=None) -> str:
    language = html.escape(metadata["language"], quote=True)
    title = html.escape(metadata["title"], quote=False)
    bodies = []
    for chapter in chapters:
        chapter_anchor = f"chapter-{chapter['index']:03d}"
        content = "\n".join(_render_block(block) for block in chapter["blocks"])
        bodies.append(f'  <section id="{chapter_anchor}" class="chapter">\n{content}\n  </section>')
    if toc_entries is not None and toc_targets is not None:
        from src.toc_editor import render_toc_markup
        toc_markup = render_toc_markup(toc_entries, toc_targets, preview=True)
    else:
        toc_markup = _toc_markup(chapters, preview=True)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src http://127.0.0.1:* http://localhost:* http://[::1]:*" />
  <title>{title} — Quick Preview</title>
  <style>{PREVIEW_CSS}</style>
</head>
<body>
  <p class="preview-note">XHTML Quick Preview ก่อนสร้าง EPUB · revision {html.escape(preview_revision)}</p>
  {('<img src="/api/jobs/' + html.escape(job_id, quote=True) + '/export/epub/cover" alt="' + html.escape(cover['alt'], quote=True) + '" />') if cover else ''}
  <nav epub:type="toc" aria-label="สารบัญ"><h1>สารบัญ</h1>
{toc_markup}
  </nav>
{os.linesep.join(bodies)}
</body>
</html>'''


def _package_opf(chapters: List[Dict[str, Any]], metadata: Dict[str, str], modified: str, cover=None) -> str:
    identifier = html.escape(metadata["identifier"], quote=False)
    title = html.escape(metadata["title"], quote=False)
    language = html.escape(metadata["language"], quote=False)
    optional = []
    if metadata.get("creator"):
        optional.append(f'    <dc:creator>{html.escape(metadata["creator"], quote=False)}</dc:creator>')
    if metadata.get("publisher"):
        optional.append(f'    <dc:publisher>{html.escape(metadata["publisher"], quote=False)}</dc:publisher>')
    if metadata.get("description"):
        optional.append(f'    <dc:description>{html.escape(metadata["description"], quote=False)}</dc:description>')
    if metadata.get("date"):
        optional.append(f'<dc:date>{html.escape(metadata["date"])}</dc:date>')
    manifest = [
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />',
        '    <item id="css" href="styles/book.css" media-type="text/css" />',
    ]
    if cover:
        manifest.extend([
            '<item id="cover-image" href="assets/cover.png" media-type="image/png" properties="cover-image" />',
            '<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml" />'])
    spine = ['<itemref idref="cover" />'] if cover else []
    for chapter in chapters:
        item_id = f"chapter-{chapter['index']:03d}"
        manifest.append(
            f'    <item id="{item_id}" href="text/{chapter["filename"]}" media-type="application/xhtml+xml" />'
        )
        spine.append(f'    <itemref idref="{item_id}" />')
    return f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="{language}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>{language}</dc:language>
{os.linesep.join(optional)}
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
{os.linesep.join(manifest)}
  </manifest>
  <spine>
{os.linesep.join(spine)}
  </spine>
</package>'''


CONTAINER_XML = '''<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>'''


def _clean_cover(cover):
    if not cover:
        return None
    if not isinstance(cover, dict):
        raise ValueError('Cover must be an object')
    encoded = str(cover.get('data_base64', ''))
    if len(encoded) > 14 * 1024 * 1024:
        raise ValueError('Cover exceeds 10 MB limit')
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 10 * 1024 * 1024:
            raise ValueError('Cover exceeds 10 MB limit')
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'PNG', 'JPEG'} or image.width * image.height > 16_000_000:
                raise ValueError('Cover must be PNG/JPEG within 16 megapixels')
            image.load()
            output = io.BytesIO()
            image.convert('RGB').save(output, format='PNG')
            clean = output.getvalue()
            if len(clean) > 20 * 1024 * 1024:
                raise ValueError('Decoded cover exceeds 20 MB limit')
            source_type = str(cover.get('source_type') or 'upload')
            if source_type not in {'upload', 'pdf_page'}:
                raise ValueError('Invalid cover source type')
            source_page = None
            if source_type == 'pdf_page':
                source_page = int(cover.get('source_page') or 0)
                if source_page < 1:
                    raise ValueError('Invalid PDF cover page')
            return {'data_base64': base64.b64encode(clean).decode('ascii'),
                    'width': image.width, 'height': image.height,
                    'alt': re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', str(cover.get('alt') or 'ปกหนังสือ'))[:300],
                    'source_type': source_type, 'source_page': source_page,
                    'sha256': _hash_bytes(clean)}
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid cover: ' + str(exc)) from exc

def _cover_xhtml(cover, metadata):
    lang = html.escape(metadata['language'], quote=True)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head><title>{html.escape(metadata['title'])}</title><link rel="stylesheet" type="text/css" href="../styles/book.css" /></head>
<body><section epub:type="cover"><img src="../assets/cover.png" alt="{html.escape(cover['alt'], quote=True)}" /></section></body></html>'''

def epub_attempt(func):
    """Expose attempt states while preserving a previously published package."""
    signature = inspect.signature(func)
    @wraps(func)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        job_dir = _safe_job_dir(bound.arguments['files_dir'], bound.arguments['job_id'])
        epub_dir = os.path.join(job_dir, 'export', 'epub')
        os.makedirs(epub_dir, exist_ok=True)
        path = os.path.join(epub_dir, 'epub_meta.json')
        previous = _read_json(path)
        atomic_write_json(path, {**previous, 'status': 'generating', 'last_error': None})
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            failed = dict(previous)
            failed.update(status='invalid' if isinstance(exc, ValueError) and not str(exc).startswith('Conflict:') else 'failed',
                          last_error=str(exc), last_attempt_status='failed')
            atomic_write_json(path, failed)
            raise
    return wrapped

@guard_artifacts
@epub_attempt
def prepare_epub_preview(
    job_id: str,
    source_variant: str = "auto",
    metadata: Optional[Dict[str, Any]] = None,
    chapter_split: str = "heading",
    files_dir: str = "files",
    cover: Optional[Dict[str, Any]] = None,
    toc_revision: Optional[str] = None,
) -> Dict[str, Any]:
    job_dir = _safe_job_dir(files_dir, job_id)
    resolved_variant, source_path, source_revision = _resolve_source(job_dir, source_variant)
    clean_metadata = _clean_metadata(metadata, job_id)
    if isinstance(cover, dict) and cover.get('reuse'):
        previous_cover = _read_json(os.path.join(job_dir, 'export', 'epub', 'preview_payload.json')).get('cover')
        if not previous_cover:
            raise ValueError('No existing cover to reuse')
        cover = {**previous_cover, 'alt': cover.get('alt') or previous_cover['alt']}
    clean_cover = _clean_cover(cover)
    with open(source_path, "r", encoding="utf-8") as stream:
        source_html = stream.read(MAX_SOURCE_BYTES + 1)
    if len(source_html.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("HTML source exceeds the 20 MB Phase 8 limit")

    blocks = _parse_blocks(source_html)
    chapters = _split_chapters(blocks, chapter_split, clean_metadata["title"])
    from src.toc_editor import automatic_entries, build_targets, load_toc, toc_revision as calculate_toc_revision, validate_entries
    toc_targets = build_targets(chapters)
    toc_path = os.path.join(job_dir, "export", "epub", "toc.json")
    saved_toc = load_toc(toc_path)
    if saved_toc.get("entries"):
        if saved_toc.get("source_revision") != source_revision:
            raise ValueError("Conflict: edited TOC is stale. Re-match and save it before Preview.")
        toc_entries = validate_entries(saved_toc["entries"], toc_targets)
        current_toc_revision = saved_toc.get("toc_revision") or calculate_toc_revision(toc_entries)
        toc_mode = "edited"
    else:
        toc_entries = validate_entries(automatic_entries(toc_targets), toc_targets)
        current_toc_revision = calculate_toc_revision(toc_entries)
        toc_mode = "automatic"
    if toc_revision is not None and toc_revision != current_toc_revision:
        raise ValueError("Conflict: TOC revision changed. Reload the TOC editor.")
    config = {
        "schema_version": EPUB_SCHEMA_VERSION,
        "source_variant": resolved_variant,
        "source_revision": source_revision,
        "chapter_split": chapter_split,
        "metadata": clean_metadata,
        "cover_sha256": clean_cover["sha256"] if clean_cover else None,
        "toc_revision": current_toc_revision,
    }
    if not clean_metadata["identifier"]:
        clean_metadata["identifier"] = "urn:sha256:" + hashlib.sha256(
            f"{job_id}:{source_revision}:{_canonical_json(config)}".encode("utf-8")
        ).hexdigest()
        config["metadata"] = clean_metadata
    preview_revision = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()[:24]
    payload_chapters = []
    for chapter in chapters:
        payload_chapters.append({
            "index": chapter["index"],
            "title": chapter["title"],
            "filename": chapter["filename"],
            "xhtml": _chapter_xhtml(chapter, clean_metadata),
        })

    nav_xhtml = _nav_xhtml(chapters, clean_metadata, clean_cover, toc_entries, toc_targets)
    preview_xhtml = _preview_xhtml(chapters, clean_metadata, preview_revision, job_id, clean_cover,
                                   toc_entries, toc_targets)
    payload = {
        **config,
        "preview_revision": preview_revision,
        "chapters": payload_chapters,
        "nav_xhtml": nav_xhtml,
        "css": BOOK_CSS,
        "cover": clean_cover,
        "toc_model": {"schema_version": "9.0", "toc_revision": current_toc_revision,
                      "mode": toc_mode, "entries": toc_entries, "targets": toc_targets},
        "book_model": {"metadata": clean_metadata, "sections": chapters,
                       "assets": [{"path": "assets/cover.png", "media_type": "image/png",
                                   "width": clean_cover["width"], "height": clean_cover["height"],
                                   "alt": clean_cover["alt"]}] if clean_cover else []},
    }

    epub_dir = os.path.join(job_dir, "export", "epub")
    os.makedirs(epub_dir, exist_ok=True)
    previous_meta = _read_json(os.path.join(epub_dir, "epub_meta.json"))
    packaged_preview_revision = previous_meta.get("packaged_preview_revision")
    package_exists = os.path.isfile(os.path.join(epub_dir, "book.epub"))
    package_is_current = bool(package_exists and packaged_preview_revision == preview_revision)
    if _source_revision(source_path) != source_revision:
        raise ValueError('Conflict: source HTML changed during preview generation.')
    atomic_write_text(os.path.join(epub_dir, "preview.xhtml"), preview_xhtml)
    atomic_write_json(os.path.join(epub_dir, "preview_payload.json"), payload)

    meta = {
        "schema_version": EPUB_SCHEMA_VERSION,
        "status": "preview_ready",
        "job_id": job_id,
        "source_variant": resolved_variant,
        "source_revision": source_revision,
        "preview_revision": preview_revision,
        "chapter_split": chapter_split,
        "toc_revision": current_toc_revision,
        "toc_mode": toc_mode,
        "toc_entries_count": len(toc_entries),
        "toc_unresolved_count": 0,
        "chapters_count": len(chapters),
        "chapters": [{"index": c["index"], "title": c["title"]} for c in chapters],
        "cover": {k: v for k, v in clean_cover.items() if k != "data_base64"} if clean_cover else None,
        "metadata": clean_metadata,
        "preview_created_at": previous_meta.get("preview_created_at") if previous_meta.get("preview_revision") == preview_revision else _utc_now(),
        "epub_ready": package_is_current,
        "package_is_stale": bool(package_exists and not package_is_current),
    }
    if packaged_preview_revision:
        meta["packaged_preview_revision"] = packaged_preview_revision
    atomic_write_json(os.path.join(epub_dir, "epub_meta.json"), meta)
    return meta


@guard_artifacts
def get_epub_preview(job_id: str, files_dir: str = "files") -> str:
    job_dir = _safe_job_dir(files_dir, job_id)
    path = os.path.join(job_dir, "export", "epub", "preview.xhtml")
    if not os.path.isfile(path):
        raise FileNotFoundError("XHTML Quick Preview not generated")
    with open(path, "r", encoding="utf-8") as stream:
        return stream.read(MAX_SOURCE_BYTES + 1)


def _safe_zip_name(name: str) -> bool:
    if not name or any(char in name for char in ('\\', ':', '%', '#', '?')) or name.startswith("/") or re.search(r'[\x00-\x1f]', name):
        return False
    normalized = posixpath.normpath(name)
    return normalized == name and normalized != ".." and not normalized.startswith("../")


def validate_epub_bytes(content: bytes) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if len(content) > MAX_PACKAGE_BYTES:
        return {'valid': False, 'errors': ['EPUB compressed size exceeds limit'], 'warnings': []}
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            infos = archive.infolist()
            if not infos:
                return {"valid": False, "errors": ["EPUB ZIP is empty"], "warnings": []}
            if len(infos) > MAX_PACKAGE_ENTRIES:
                errors.append("EPUB contains too many entries")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("EPUB contains duplicate paths")
            if any(not _safe_zip_name(name) for name in names):
                errors.append("EPUB contains an unsafe path")
            if sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES:
                errors.append("EPUB uncompressed size exceeds limit")
            if errors:
                return {'valid': False, 'errors': errors, 'warnings': warnings}
            first = infos[0]
            if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
                errors.append("mimetype must be the first uncompressed ZIP entry")
            elif archive.read("mimetype") != b"application/epub+zip":
                errors.append("Invalid EPUB mimetype")

            required = {"mimetype", "META-INF/container.xml", "EPUB/package.opf", "EPUB/nav.xhtml"}
            missing = sorted(required.difference(names))
            if missing:
                errors.append("Missing required files: " + ", ".join(missing))

            for name in names:
                if name.endswith('.css') and re.search(r'@import|\burl\s*\(', archive.read(name).decode('utf-8'), re.I):
                    errors.append('Unsafe CSS resource: ' + name)
                if name.endswith((".xml", ".opf", ".xhtml")):
                    try:
                        ET.fromstring(archive.read(name))
                    except ET.ParseError as exc:
                        errors.append(f"Invalid XML in {name}: {exc}")

            if "EPUB/package.opf" in names:
                root = ET.fromstring(archive.read("EPUB/package.opf"))
                ns = {"opf": "http://www.idpf.org/2007/opf"}
                manifest = {
                    item.get("id"): item.get("href")
                    for item in root.findall(".//opf:manifest/opf:item", ns)
                }
                for item_id, href in manifest.items():
                    target = posixpath.normpath(posixpath.join("EPUB", href or ""))
                    if not item_id or not href or not _safe_zip_name(target) or target not in names:
                        errors.append(f"Invalid manifest item: {item_id or '<missing id>'}")
                for itemref in root.findall(".//opf:spine/opf:itemref", ns):
                    if itemref.get("idref") not in manifest:
                        errors.append(f"Spine idref not found: {itemref.get('idref')}")
                declared = {posixpath.normpath(posixpath.join('EPUB', href or '')) for href in manifest.values()}
                extras = set(names) - declared - {'mimetype', 'META-INF/container.xml', 'EPUB/package.opf'}
                if extras:
                    errors.append('Orphan resources: ' + ', '.join(sorted(extras)))
                container = ET.fromstring(archive.read('META-INF/container.xml'))
                paths = [element.get('full-path') for element in container.iter() if element.tag.endswith('rootfile')]
                if paths != ['EPUB/package.opf']:
                    errors.append('Container must reference the package OPF')
                documents = {}
                ids = {}
                for name in names:
                    if name.endswith('.xhtml'):
                        document = ET.fromstring(archive.read(name))
                        documents[name] = document
                        values = [element.get('id') for element in document.iter() if element.get('id')]
                        if len(values) != len(set(values)):
                            errors.append('Duplicate XHTML IDs: ' + name)
                        ids[name] = set(values)
                for name, document in documents.items():
                    for element in document.iter():
                        tag = element.tag.rsplit('}', 1)[-1]
                        if tag in DISCARD_CONTENT_TAGS - {'head', 'style'} or any(attr.lower().startswith('on') for attr in element.attrib):
                            errors.append('Active content in ' + name)
                        for attribute in ('href', 'src'):
                            reference = element.get(attribute)
                            if reference is None:
                                continue
                            parts = urlsplit(reference)
                            if parts.scheme or parts.netloc:
                                errors.append('External resource/link: ' + reference)
                                continue
                            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), parts.path)) if parts.path else name
                            if not _safe_zip_name(target) or target not in names:
                                errors.append('Missing or unsafe reference: ' + reference)
                            elif parts.fragment and parts.fragment not in ids.get(target, set()):
                                errors.append('Missing fragment: ' + reference)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, ET.ParseError) as exc:
        errors.append(f"Invalid EPUB package: {exc}")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@guard_artifacts
@epub_attempt
def build_epub(
    job_id: str,
    base_preview_revision: str,
    files_dir: str = "files",
) -> Dict[str, Any]:
    job_dir = _safe_job_dir(files_dir, job_id)
    epub_dir = os.path.join(job_dir, "export", "epub")
    payload_path = os.path.join(epub_dir, "preview_payload.json")
    payload = _read_json(payload_path)
    if not payload:
        raise FileNotFoundError("XHTML Quick Preview not generated")
    preview_revision = payload.get("preview_revision")
    if not base_preview_revision or base_preview_revision != preview_revision:
        raise ValueError("Conflict: preview revision does not match. Generate Quick Preview again.")

    _, source_path, current_source_revision = _resolve_source(job_dir, str(payload.get("source_variant", "basic")))
    if current_source_revision != payload.get("source_revision"):
        raise ValueError("Conflict: source HTML changed after Quick Preview.")
    toc_model = payload.get("toc_model") if isinstance(payload.get("toc_model"), dict) else {}
    from src.toc_editor import load_toc, toc_revision as calculate_toc_revision, validate_entries
    if toc_model:
        validate_entries(toc_model.get("entries"), toc_model.get("targets") or [])
    saved_toc = load_toc(os.path.join(epub_dir, "toc.json"))
    if saved_toc.get("entries"):
        current_toc_revision = saved_toc.get("toc_revision") or calculate_toc_revision(saved_toc["entries"])
        if current_toc_revision != payload.get("toc_revision"):
            raise ValueError("Conflict: TOC changed after Quick Preview.")

    chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    if not chapters:
        raise ValueError("Quick Preview contains no chapters")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    modified = _read_json(os.path.join(epub_dir, "epub_meta.json")).get("preview_created_at") or _utc_now()
    cover = payload.get("cover")
    opf = _package_opf(chapters, metadata, modified, cover)

    buffer = io.BytesIO()
    class DeterministicZip(zipfile.ZipFile):
        def writestr(self, name, data, **kwargs):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            return super().writestr(info, data, **kwargs)
    with DeterministicZip(buffer, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER_XML.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/package.opf", opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/nav.xhtml", str(payload.get("nav_xhtml", "")).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/styles/book.css", str(payload.get("css", BOOK_CSS)).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        if cover:
            archive.writestr('EPUB/assets/cover.png', base64.b64decode(cover['data_base64']), compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr('EPUB/text/cover.xhtml', _cover_xhtml(cover, metadata).encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
        for chapter in chapters:
            filename = str(chapter.get("filename", ""))
            target = f"EPUB/text/{filename}"
            if not _safe_zip_name(target):
                raise ValueError("Unsafe chapter path")
            archive.writestr(target, str(chapter.get("xhtml", "")).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)

    package_bytes = buffer.getvalue()
    validation = validate_epub_bytes(package_bytes)
    if not validation["valid"]:
        raise ValueError("EPUB validation failed: " + "; ".join(validation["errors"]))

    output_path = os.path.join(epub_dir, "book.epub")
    if _source_revision(source_path) != current_source_revision or _read_json(payload_path).get('preview_revision') != preview_revision:
        raise ValueError('Conflict: source or preview changed during packaging.')
    previous_package = None
    if os.path.isfile(output_path):
        with open(output_path, 'rb') as stream:
            previous_package = stream.read()
    atomic_write_bytes(output_path, package_bytes)
    meta_path = os.path.join(epub_dir, "epub_meta.json")
    meta = _read_json(meta_path)
    meta.update({
        "status": "ready",
        "preview_revision": preview_revision,
        "packaged_preview_revision": preview_revision,
        "source_revision": current_source_revision,
        "generated_at": modified,
        "epub_ready": True,
        "file_size": len(package_bytes),
        "sha256": _hash_bytes(package_bytes),
        "validation": validation,
    })
    try:
        atomic_write_json(meta_path, meta)
    except Exception:
        if previous_package is not None:
            atomic_write_bytes(output_path, previous_package)
        raise
    return meta


def get_epub_status(job_id: str, files_dir: str = "files") -> Dict[str, Any]:
    job_dir = _safe_job_dir(files_dir, job_id)
    epub_dir = os.path.join(job_dir, "export", "epub")
    meta = _read_json(os.path.join(epub_dir, "epub_meta.json"))
    if not meta:
        return {
            "job_id": job_id,
            "status": "not_generated",
            "preview_ready": False,
            "epub_ready": False,
            "is_stale": False,
        }

    is_stale = False
    try:
        _, source_path, current_revision = _resolve_source(job_dir, str(meta.get("source_variant", "basic")))
        is_stale = current_revision != meta.get("source_revision")
    except (FileNotFoundError, ValueError):
        is_stale = True
    from src.toc_editor import load_toc, toc_revision as calculate_toc_revision
    saved_toc = load_toc(os.path.join(epub_dir, "toc.json"))
    if saved_toc.get("entries"):
        current_toc_revision = saved_toc.get("toc_revision") or calculate_toc_revision(saved_toc["entries"])
        is_stale = is_stale or current_toc_revision != meta.get("toc_revision")
    package_exists = os.path.isfile(os.path.join(epub_dir, "book.epub"))
    package_is_current = bool(
        package_exists
        and meta.get("packaged_preview_revision")
        and meta.get("packaged_preview_revision") == meta.get("preview_revision")
    )
    if meta.get('status') == 'generating':
        current_status = 'generating'
    elif is_stale and meta.get('source_revision'):
        current_status = "stale"
    elif package_is_current:
        current_status = "ready"
    elif meta.get('status') in {'failed', 'invalid'}:
        current_status = meta['status']
    else:
        current_status = "preview_ready"
    result = dict(meta)
    result.update({
        "job_id": job_id,
        "status": current_status,
        "preview_ready": os.path.isfile(os.path.join(epub_dir, "preview.xhtml")),
        "epub_ready": bool(package_is_current and not is_stale),
        "package_is_stale": bool(package_exists and (not package_is_current or is_stale)),
        "is_stale": is_stale,
    })
    return result
