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
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit

from src.file_utils import atomic_write_bytes, atomic_write_json, atomic_write_text


EPUB_SCHEMA_VERSION = "8.0"
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 1000
ALLOWED_SOURCE_VARIANTS = {"auto", "basic", "ai", "final"}
ALLOWED_CHAPTER_SPLITS = {"heading", "page"}
BLOCK_TAGS = {"p", "h1", "h2", "h3"}
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
.pre-wrap { white-space: pre-wrap; }
.page-marker { color: #666; font-style: italic; }
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
    return {
        "title": title or f"OCR Document {job_id}",
        "language": language,
        "identifier": identifier,
        "creator": clean("creator", "", 300),
        "publisher": clean("publisher", "", 300),
        "description": clean("description", "", 2000),
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
        raise ValueError("Allowed EPUB source variants: auto, basic, ai, final")

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
        path = os.path.join(export_dir, f"{candidate}.html")
        if os.path.isfile(path):
            return candidate, path, _source_revision(path)

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
                "inner": [],
                "text": [],
            }
            return
        if self.current is None:
            return
        if tag in INLINE_TAGS:
            link_attr = ""
            if tag == "a":
                href = attr_map.get("href", "").strip()
                if not re.search(r"[\x00-\x20\x7f]", href):
                    try:
                        parts = urlsplit(href)
                        if (parts.scheme in {"http", "https"} and parts.netloc) or (parts.scheme == "mailto" and parts.path):
                            link_attr = f' href="{html.escape(href, quote=True)}"'
                    except ValueError:
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
        if self.discard_depth or self.current is None:
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
        raise ValueError("HTML source contains no exportable p/h1/h2/h3 content")

    heading_index = 0
    last_level = 0
    for block in parser.blocks:
        tag = block["tag"]
        if tag.startswith("h"):
            level = int(tag[1])
            if last_level and level - last_level > 1:
                raise ValueError(f"Heading hierarchy jumps from h{last_level} to h{level}")
            last_level = level
            heading_index += 1
            block["id"] = f"heading-{heading_index:04d}"
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


def _nav_xhtml(chapters: List[Dict[str, Any]], metadata: Dict[str, str]) -> str:
    language = html.escape(metadata["language"], quote=True)
    title = html.escape(metadata["title"], quote=False)
    items: List[str] = []
    for chapter in chapters:
        label = html.escape(chapter["title"], quote=False)
        headings = [b for b in chapter["blocks"] if b.get("id") and b.get("tag") in {"h1", "h2", "h3"}]
        first_id = headings[0].get("id") if headings else None
        fragment = f"#{first_id}" if first_id else ""
        children = []
        for heading in headings[1:]:
            heading_label = html.escape(heading["visible_text"], quote=False)
            children.append(
                f'          <li><a href="text/{chapter["filename"]}#{heading["id"]}">{heading_label}</a></li>'
            )
        child_html = f"\n        <ol>\n{os.linesep.join(children)}\n        </ol>" if children else ""
        items.append(f'      <li><a href="text/{chapter["filename"]}{fragment}">{label}</a>{child_html}</li>')
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">
<head><meta charset="utf-8" /><title>{title}</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>สารบัญ</h1>
    <ol>
{os.linesep.join(items)}
    </ol>
  </nav>
</body>
</html>'''


def _preview_xhtml(chapters: List[Dict[str, Any]], metadata: Dict[str, str], preview_revision: str) -> str:
    language = html.escape(metadata["language"], quote=True)
    title = html.escape(metadata["title"], quote=False)
    toc_items = []
    bodies = []
    for chapter in chapters:
        chapter_anchor = f"chapter-{chapter['index']:03d}"
        label = html.escape(chapter["title"], quote=False)
        child_links = []
        headings = [b for b in chapter["blocks"] if b.get("id") and b.get("tag") in {"h1", "h2", "h3"}]
        for heading in headings[1:]:
            heading_label = html.escape(heading["visible_text"], quote=False)
            child_links.append(f'          <li><a href="#{heading["id"]}">{heading_label}</a></li>')
        child_html = f"\n        <ol>\n{os.linesep.join(child_links)}\n        </ol>" if child_links else ""
        toc_items.append(f'      <li><a href="#{chapter_anchor}">{label}</a>{child_html}</li>')
        content = "\n".join(_render_block(block) for block in chapter["blocks"])
        bodies.append(f'  <section id="{chapter_anchor}" class="chapter">\n{content}\n  </section>')
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'" />
  <title>{title} — Quick Preview</title>
  <style>{PREVIEW_CSS}</style>
</head>
<body>
  <p class="preview-note">XHTML Quick Preview ก่อนสร้าง EPUB · revision {html.escape(preview_revision)}</p>
  <nav epub:type="toc"><h1>สารบัญ</h1><ol>
{os.linesep.join(toc_items)}
  </ol></nav>
{os.linesep.join(bodies)}
</body>
</html>'''


def _package_opf(chapters: List[Dict[str, Any]], metadata: Dict[str, str], modified: str) -> str:
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
    manifest = [
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />',
        '    <item id="css" href="styles/book.css" media-type="text/css" />',
    ]
    spine = []
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


def prepare_epub_preview(
    job_id: str,
    source_variant: str = "auto",
    metadata: Optional[Dict[str, Any]] = None,
    chapter_split: str = "heading",
    files_dir: str = "files",
) -> Dict[str, Any]:
    job_dir = _safe_job_dir(files_dir, job_id)
    resolved_variant, source_path, source_revision = _resolve_source(job_dir, source_variant)
    clean_metadata = _clean_metadata(metadata, job_id)
    config = {
        "schema_version": EPUB_SCHEMA_VERSION,
        "source_variant": resolved_variant,
        "source_revision": source_revision,
        "chapter_split": chapter_split,
        "metadata": clean_metadata,
    }
    if not clean_metadata["identifier"]:
        clean_metadata["identifier"] = "urn:sha256:" + hashlib.sha256(
            f"{job_id}:{source_revision}:{_canonical_json(config)}".encode("utf-8")
        ).hexdigest()
        config["metadata"] = clean_metadata
    preview_revision = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()[:24]

    with open(source_path, "r", encoding="utf-8") as stream:
        source_html = stream.read(MAX_SOURCE_BYTES + 1)
    if len(source_html.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("HTML source exceeds the 20 MB Phase 8 limit")

    blocks = _parse_blocks(source_html)
    chapters = _split_chapters(blocks, chapter_split, clean_metadata["title"])
    payload_chapters = []
    for chapter in chapters:
        payload_chapters.append({
            "index": chapter["index"],
            "title": chapter["title"],
            "filename": chapter["filename"],
            "xhtml": _chapter_xhtml(chapter, clean_metadata),
        })

    nav_xhtml = _nav_xhtml(chapters, clean_metadata)
    preview_xhtml = _preview_xhtml(chapters, clean_metadata, preview_revision)
    payload = {
        **config,
        "preview_revision": preview_revision,
        "chapters": payload_chapters,
        "nav_xhtml": nav_xhtml,
        "css": BOOK_CSS,
    }

    epub_dir = os.path.join(job_dir, "export", "epub")
    os.makedirs(epub_dir, exist_ok=True)
    previous_meta = _read_json(os.path.join(epub_dir, "epub_meta.json"))
    packaged_preview_revision = previous_meta.get("packaged_preview_revision")
    package_exists = os.path.isfile(os.path.join(epub_dir, "book.epub"))
    package_is_current = bool(package_exists and packaged_preview_revision == preview_revision)
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
        "chapters_count": len(chapters),
        "metadata": clean_metadata,
        "preview_created_at": _utc_now(),
        "epub_ready": package_is_current,
        "package_is_stale": bool(package_exists and not package_is_current),
    }
    if packaged_preview_revision:
        meta["packaged_preview_revision"] = packaged_preview_revision
    atomic_write_json(os.path.join(epub_dir, "epub_meta.json"), meta)
    return meta


def get_epub_preview(job_id: str, files_dir: str = "files") -> str:
    job_dir = _safe_job_dir(files_dir, job_id)
    path = os.path.join(job_dir, "export", "epub", "preview.xhtml")
    if not os.path.isfile(path):
        raise FileNotFoundError("XHTML Quick Preview not generated")
    with open(path, "r", encoding="utf-8") as stream:
        return stream.read(MAX_SOURCE_BYTES + 1)


def _safe_zip_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    normalized = posixpath.normpath(name)
    return normalized == name and normalized != ".." and not normalized.startswith("../")


def validate_epub_bytes(content: bytes) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
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
    except (zipfile.BadZipFile, KeyError, OSError, ET.ParseError) as exc:
        errors.append(f"Invalid EPUB package: {exc}")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


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

    chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    if not chapters:
        raise ValueError("Quick Preview contains no chapters")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    modified = _utc_now()
    opf = _package_opf(chapters, metadata, modified)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER_XML.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/package.opf", opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/nav.xhtml", str(payload.get("nav_xhtml", "")).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/styles/book.css", str(payload.get("css", BOOK_CSS)).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
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
    atomic_write_json(meta_path, meta)
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
    package_exists = os.path.isfile(os.path.join(epub_dir, "book.epub"))
    package_is_current = bool(
        package_exists
        and meta.get("packaged_preview_revision")
        and meta.get("packaged_preview_revision") == meta.get("preview_revision")
    )
    if is_stale:
        current_status = "stale"
    elif package_is_current:
        current_status = "ready"
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
