"""
HTML Export module for Local Thai OCR Web (Phase 7).
Provides:
1. Deterministic basic HTML export (basic.html) using font metrics, layout signals, and PDF text layer.
2. AI-assisted semantic HTML export (ai.html) via Local LLM annotations with strict validator.
3. User-edited final HTML export (final.html).
4. Strict XSS defense, CSP headers, sandboxed preview, and UTF-8 verification.
"""

import os
import re
import json
import html
from html.parser import HTMLParser
import hashlib
import difflib
import statistics
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone

from src.file_utils import atomic_write_text, atomic_write_json
from src.thai_ocr_normalizer import normalize_ocr_line


ALLOWED_TAGS = {"p", "h1", "h2", "h3", "b", "i", "span", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "ul", "ol", "li"}
ALLOWED_ATTRIBUTES = {"lang", "charset", "id", "class", "data-page", "data-src", "data-edited", "rowspan", "colspan"}

# Regex for illegal control characters (retain \t, \n; strip NUL, C0 controls)
ILLEGAL_CTRL_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Standard Thai chapter / section heading prefix pattern
THAI_HEADING_PATTERN = re.compile(
    r"^(บทที่|ตอนที่|ส่วนที่|ภาคผนวก|หัวข้อที่|\d+(\.\d+)*)\s+",
    re.IGNORECASE
)


def sanitize_text(text: str) -> str:
    """Strips illegal HTML control characters and escapes HTML entities."""
    if not text:
        return ""
    cleaned = ILLEGAL_CTRL_REGEX.sub("", text)
    return html.escape(cleaned, quote=True)


def compute_source_revision(job_dir: str) -> str:
    """Computes a SHA-256 hash representing the revision of final.txt across all pages."""
    final_path = os.path.join(job_dir, "final.txt")
    if os.path.exists(final_path):
        with open(final_path, "r", encoding="utf-8") as f:
            content = f.read()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return "empty"


def get_html_document_shell(title: str, body_content: str) -> str:
    """
    Renders standard, offline-compliant HTML shell with:
    - <!doctype html> and <html lang="th">
    - UTF-8 charset
    - Content-Security-Policy (default-src 'none'; style-src 'unsafe-inline';)
    - Embedded offline CSS using system Thai fonts and @media print
    - Escaped title
    """
    escaped_title = sanitize_text(title or "OCR Document")
    return f"""<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --font-family: 'TH Sarabun New', 'Leelawadee UI', Tahoma, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --line-height: 1.6;
      --text-color: #212529;
      --bg-color: #f8f9fa;
      --page-bg: #ffffff;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: var(--font-family);
      color: var(--text-color);
      background-color: var(--bg-color);
      line-height: var(--line-height);
      margin: 0;
      padding: 2rem 1rem;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
    }}
    .page-container {{
      background: var(--page-bg);
      padding: 3rem 3.5rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      border-radius: 8px;
    }}
    h1, h2, h3 {{
      color: #111827;
      margin-top: 1.4em;
      margin-bottom: 0.6em;
      line-height: 1.3;
    }}
    h1 {{
      font-size: 1.85rem;
      font-weight: 700;
      margin-top: 0.5em;
    }}
    h2 {{
      font-size: 1.45rem;
      font-weight: 700;
    }}
    h3 {{
      font-size: 1.2rem;
      font-weight: 600;
    }}
    p {{
      margin-top: 0;
      margin-bottom: 0.9em;
      text-align: justify;
      word-break: break-word;
    }}
    p.pre-wrap {{
      white-space: pre-wrap;
    }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #999; padding: 0.4rem; vertical-align: top; }}
    th {{ background: #eee; font-weight: 700; }}
    .page-marker {{
      color: #6c757d;
      font-style: italic;
      padding: 0.75rem 1rem;
      background: #f1f3f5;
      border-left: 4px solid #ced4da;
      border-radius: 4px;
    }}
    .page-failed {{
      background: #fff5f5;
      border: 1px dashed #ffa8a8;
      border-radius: 8px;
      padding: 2rem;
      margin-bottom: 2rem;
    }}
    b {{
      font-weight: 700;
    }}
    i {{
      font-style: italic;
    }}
    @media print {{
      body {{
        background: transparent;
        padding: 0;
      }}
      .page-container {{
        box-shadow: none;
        padding: 0;
        margin-bottom: 0;
        page-break-after: always;
      }}
      .page-container:last-child {{
        page-break-after: avoid;
      }}
    }}
  </style>
</head>
<body>
<main>
{body_content}
</main>
</body>
</html>"""


def calculate_page_body_size(blocks: List[Dict[str, Any]]) -> float:
    """Computes median font size weighted by character length across lines on the page."""
    sizes: List[float] = []
    for b in blocks:
        for l in b.get("lines", []):
            st = l.get("style", {})
            sm = st.get("size_median", 0.0)
            text_len = len(l.get("text", "").strip())
            if sm > 0.0 and text_len > 0:
                sizes.extend([sm] * text_len)
    return round(statistics.median(sizes), 2) if sizes else 14.0


def clean_page_text(text: str, page_num: int) -> str:
    """Strips internal page header artifact if present."""
    prefix = f"--- Page {page_num} ---"
    stripped = text.strip()
    if stripped.lower().startswith(prefix.lower()):
        return stripped[len(prefix):].lstrip(" \t\r\n")
    return stripped


def determine_line_heading(
    text: str,
    style: Dict[str, Any],
    body_size: float,
    is_first_line_on_page: bool,
    gap_above_ratio: float = 1.0,
) -> Optional[str]:
    """
    Evaluates whether a line qualifies as a heading based on >= 2 independent signals:
    Signal 1: Font size >= 1.2 * body_size
    Signal 2: Bold ratio >= 0.8
    Signal 3: Spacing gap above >= 1.5 normal line height or is first line
    Signal 4: Thai heading pattern (บทที่/ตอนที่/เลขลำดับ)
    
    Negative filters:
    - Length > 80 chars
    - More than 2 lines (evaluated at line level)
    - Ends with trailing full stop / period
    """
    clean_t = text.strip()
    if not clean_t or len(clean_t) > 80:
        return None
    if clean_t.endswith(".") and not re.search(r"\b[A-Za-z0-9]\.$", clean_t):
        return None

    signals = 0
    size_median = style.get("size_median", 0.0)
    bold_ratio = style.get("bold_ratio", 0.0)

    # Signal 1: Size
    if body_size > 0 and size_median >= 1.2 * body_size:
        signals += 1

    # Signal 2: Bold
    if bold_ratio >= 0.8:
        signals += 1

    # Signal 3: Spacing / Position
    if is_first_line_on_page or gap_above_ratio >= 1.5:
        signals += 1

    # Signal 4: Pattern
    if THAI_HEADING_PATTERN.match(clean_t):
        signals += 1

    if signals >= 2:
        ratio = (size_median / body_size) if body_size > 0 else 1.0
        if ratio >= 1.2 or (bold_ratio >= 0.8 and is_first_line_on_page):
            return "h1_candidate"
        elif ratio >= 1.1 or bold_ratio >= 0.8 or THAI_HEADING_PATTERN.match(clean_t):
            return "h2"
        else:
            return "h3"

    return None


def format_inline_styles(text: str, style: Dict[str, Any]) -> str:
    """
    Formats line text with <b> or <i> tags based on style ratios or spans.
    Guarantees that the textual content of final.txt is 100% preserved.
    """
    bold_ratio = style.get("bold_ratio", 0.0)
    italic_ratio = style.get("italic_ratio", 0.0)
    evidence = style.get("evidence", "none")
    spans = style.get("spans", [])

    if evidence == "none" or not text:
        return sanitize_text(text)

    # Line-level wrap
    if bold_ratio >= 0.8:
        escaped = sanitize_text(text)
        if italic_ratio >= 0.8:
            return f"<b><i>{escaped}</i></b>"
        return f"<b>{escaped}</b>"

    if italic_ratio >= 0.8:
        return f"<i>{sanitize_text(text)}</i>"

    # Span-level wrap if available
    # CRITICAL: only use span decomposition if spans match 'text' verbatim,
    # ensuring user edits from final.txt are never overwritten or lost!
    if spans:
        spans_combined_text = "".join(s.get("text", "") for s in spans)
        if spans_combined_text == text:
            pieces = []
            for s in spans:
                s_text = s.get("text", "")
                if not s_text:
                    continue
                esc = sanitize_text(s_text)
                if s.get("is_bold") and s.get("is_italic"):
                    pieces.append(f"<b><i>{esc}</i></b>")
                elif s.get("is_bold"):
                    pieces.append(f"<b>{esc}</b>")
                elif s.get("is_italic"):
                    pieces.append(f"<i>{esc}</i>")
                else:
                    pieces.append(esc)
            return "".join(pieces)

    return sanitize_text(text)


def reconcile_final_lines_with_blocks(
    final_lines: List[str],
    blocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Reconciles final text lines with source blocks using line-level sequence matching.
    Preserves final text 100% while attaching block_id, typography style, and edit tracking.
    """
    # Flatten source block lines
    src_lines = []
    for b in blocks:
        b_id = b.get("block_id", "")
        for l in b.get("lines", []):
            src_lines.append({
                "block_id": b_id,
                "text": l.get("text", "").strip(),
                "style": l.get("style", {}),
            })

    # Prepare return list
    src_texts = [s["text"] for s in src_lines]
    fin_stripped = [f.strip() for f in final_lines]

    # Fast path: exact match without expensive SequenceMatcher
    if src_texts == fin_stripped:
        return [
            {
                "text": final_lines[i],
                "block_id": src_lines[i]["block_id"],
                "style": src_lines[i]["style"],
                "is_edited": False,
            }
            for i in range(len(final_lines))
        ]

    reconciled = []
    matcher = difflib.SequenceMatcher(None, src_texts, fin_stripped)
    opcodes = matcher.get_opcodes()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for src_idx, fin_idx in zip(range(i1, i2), range(j1, j2)):
                reconciled.append({
                    "text": final_lines[fin_idx],
                    "block_id": src_lines[src_idx]["block_id"],
                    "style": src_lines[src_idx]["style"],
                    "is_edited": False,
                })
        elif tag == "replace":
            # Check near matches
            for fin_idx in range(j1, j2):
                fin_t = final_lines[fin_idx].strip()
                best_match = None
                best_ratio = 0.0
                for src_idx in range(i1, i2):
                    r = difflib.SequenceMatcher(None, src_lines[src_idx]["text"], fin_t).ratio()
                    if r > best_ratio:
                        best_ratio = r
                        best_match = src_lines[src_idx]

                if best_match and best_ratio >= 0.7:
                    reconciled.append({
                        "text": final_lines[fin_idx],
                        "block_id": best_match["block_id"],
                        "style": best_match["style"],
                        "is_edited": best_ratio < 0.99,
                    })
                else:
                    reconciled.append({
                        "text": final_lines[fin_idx],
                        "block_id": "",
                        "style": {},
                        "is_edited": True,
                    })
        elif tag == "insert":
            for fin_idx in range(j1, j2):
                reconciled.append({
                    "text": final_lines[fin_idx],
                    "block_id": "",
                    "style": {},
                    "is_edited": True,
                })
        # tag == 'delete' is omitted because text must come from final.txt 100%

    return reconciled


def render_page_section(
    page_num: int,
    reconciled_units: List[Dict[str, Any]],
    doc_has_h1: bool,
    body_size: float,
    status: str = "completed",
    error_marker: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Renders HTML <section> for a single page.
    Returns (section_html, updated_doc_has_h1).
    """
    if status in ("failed", "cancelled") or error_marker:
        marker = sanitize_text(error_marker or f"[หน้า {page_num}: ประมวลผลไม่สำเร็จหรือถูกยกเลิก]")
        sec = f'  <section id="page-{page_num}" data-page="{page_num}" class="page-container page-failed">\n    <p class="page-marker">{marker}</p>\n  </section>'
        return sec, doc_has_h1

    if not reconciled_units:
        sec = f'  <section id="page-{page_num}" data-page="{page_num}" class="page-container">\n    <p class="page-marker">[หน้า {page_num}: หน้าว่าง / ไม่มีข้อความ]</p>\n  </section>'
        return sec, doc_has_h1

    lines_html = []
    is_first_line = True
    last_heading_level = 0

    for idx, u in enumerate(reconciled_units):
        text = u["text"]
        if not text.strip():
            continue

        style = u.get("style", {})
        block_id = u.get("block_id", "")
        is_edited = u.get("is_edited", False)

        # Attribute formation
        data_attrs = []
        if block_id:
            data_attrs.append(f'data-src="{sanitize_text(block_id)}"')
        if is_edited:
            data_attrs.append('data-edited="1"')
        attr_str = (" " + " ".join(data_attrs)) if data_attrs else ""

        # Check for tab or table pre-wrap formatting
        is_pre_wrap = "\t" in text

        # Heading detection
        heading = determine_line_heading(
            text=text,
            style=style,
            body_size=body_size,
            is_first_line_on_page=is_first_line,
        )

        content_html = format_inline_styles(text, style)

        if heading:
            if heading == "h1_candidate":
                if not doc_has_h1:
                    tag = "h1"
                    doc_has_h1 = True
                    last_heading_level = 1
                else:
                    tag = "h2"
                    last_heading_level = 2
            elif heading == "h2":
                tag = "h2"
                last_heading_level = 2
            else:
                # Prevent heading jump: if no prior heading, start at h2
                tag = "h3" if last_heading_level >= 2 else "h2"
                last_heading_level = int(tag[1])

            lines_html.append(f'    <{tag}{attr_str}>{content_html}</{tag}>')
        else:
            p_class = ' class="pre-wrap"' if is_pre_wrap else ""
            lines_html.append(f'    <p{p_class}{attr_str}>{content_html}</p>')

        is_first_line = False

    inner = "\n".join(lines_html)
    sec = f'  <section id="page-{page_num}" data-page="{page_num}" class="page-container">\n{inner}\n  </section>'
    return sec, doc_has_h1


def generate_basic_html(job_id: str, files_dir: str = "files") -> Tuple[str, Dict[str, Any]]:
    """
    Generates deterministic basic.html from job outputs without calling AI.
    Byte-identical guarantee for identical input data.
    """
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    if not os.path.exists(job_dir):
        raise FileNotFoundError(f"Job directory not found: {job_dir}")

    # Read ocr.json to get page blocks & metadata
    ocr_path = os.path.join(job_dir, "ocr.json")
    pages_ocr: List[Dict[str, Any]] = []
    if os.path.exists(ocr_path):
        try:
            with open(ocr_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                pages_ocr = ocr_data.get("pages", [])
        except Exception:
            pages_ocr = []

    # Map page_num to page ocr data
    ocr_by_num: Dict[int, Dict[str, Any]] = {}
    for p in pages_ocr:
        ocr_by_num[p.get("page_id", 1)] = p

    # Find all page directories
    page_dirs = sorted([
        d for d in os.listdir(job_dir)
        if os.path.isdir(os.path.join(job_dir, d)) and d.startswith("page_")
    ])

    sections = []
    doc_has_h1 = False
    total_chars = 0

    for pd_name in page_dirs:
        m = re.match(r"page_(\d+)", pd_name)
        if not m:
            continue
        p_num = int(m.group(1))
        pd_path = os.path.join(job_dir, pd_name)

        # Read page final.txt
        final_txt_path = os.path.join(pd_path, "final.txt")
        final_content = ""
        if os.path.exists(final_txt_path):
            with open(final_txt_path, "r", encoding="utf-8") as f:
                final_content = f.read()

        total_chars += len(final_content)

        # Check for error / failed / cancelled marker
        error_marker = None
        upper_content = final_content.upper()
        if (
            "[FAILED:" in upper_content
            or "CANCELLED" in upper_content
            or "[BLANK]" in upper_content
            or "PROCESSING FAILED" in upper_content
        ):
            error_marker = final_content.strip()

        # Get blocks
        p_ocr = ocr_by_num.get(p_num, {})
        p_blocks = p_ocr.get("blocks", [])

        # Reconcile lines
        cleaned_final = clean_page_text(final_content, p_num)
        final_lines = [l for l in cleaned_final.split("\n") if l.strip()]
        reconciled = reconcile_final_lines_with_blocks(final_lines, p_blocks)
        body_size = calculate_page_body_size(p_blocks)

        sec_html, doc_has_h1 = render_page_section(
            page_num=p_num,
            reconciled_units=reconciled,
            doc_has_h1=doc_has_h1,
            body_size=body_size,
            status="completed" if not error_marker else "failed",
            error_marker=error_marker,
        )
        sections.append(sec_html)

    body_content = "\n".join(sections)
    title = f"Document {job_id}"
    full_html = get_html_document_shell(title=title, body_content=body_content)

    # Save to files/{job_id}/export/basic.html if changed or missing
    export_dir = os.path.join(job_dir, "export")
    os.makedirs(export_dir, exist_ok=True)
    basic_path = os.path.join(export_dir, "basic.html")
    should_write = True
    if os.path.exists(basic_path):
        try:
            with open(basic_path, "r", encoding="utf-8") as bf:
                if bf.read() == full_html:
                    should_write = False
        except Exception:
            should_write = True
    if should_write:
        atomic_write_text(basic_path, full_html)

    html_hash = hashlib.sha256(full_html.encode("utf-8")).hexdigest()
    src_rev = compute_source_revision(job_dir)

    meta = {
        "job_id": job_id,
        "mode": "basic",
        "hash": html_hash,
        "source_revision": src_rev,
        "total_chars": total_chars,
        "pages_count": len(page_dirs),
    }

    _update_export_meta(job_dir, "basic", meta)
    return full_html, meta


class AIAnnotationValidator:
    """
    Validates annotations returned by Local LLM against strict security and schema criteria:
    - Allowed tags only: p, h1, h2, h3
    - Units must exist in input
    - Maximum 1 h1 in entire document
    - Hierarchy checks (no jumping h1 -> h3)
    - No script or attribute injections
    """
    def __init__(self, valid_units: List[str]):
        self.valid_units = set(valid_units)

    def validate(self, annotations: Any) -> Tuple[bool, str, List[Dict[str, str]]]:
        if not isinstance(annotations, list):
            return False, "Annotations must be a JSON array", []

        h1_count = 0
        seen_units = set()
        sanitized_list = []
        last_level = 0

        for item in annotations:
            if not isinstance(item, dict):
                return False, "Each annotation must be a JSON object", []

            unit_id = item.get("unit")
            tag = str(item.get("tag", "")).lower().strip()

            if not unit_id or unit_id not in self.valid_units:
                return False, f"Invalid or unknown unit: '{unit_id}'", []

            if unit_id in seen_units:
                return False, f"Duplicate unit annotation: '{unit_id}'", []
            seen_units.add(unit_id)

            if tag not in ("p", "h1", "h2", "h3"):
                return False, f"Prohibited tag '{tag}'. Only p, h1, h2, h3 allowed", []

            if tag == "h1":
                h1_count += 1
                if h1_count > 1:
                    return False, "Multiple h1 tags are forbidden across document", []

            # Check heading hierarchy jumping (e.g. h1 -> h3)
            if tag in ("h1", "h2", "h3"):
                curr_level = int(tag[1])
                if last_level > 0 and curr_level - last_level > 1:
                    return False, f"Heading hierarchy jumped from h{last_level} to h{curr_level}", []
                last_level = curr_level

            sanitized_list.append({"unit": unit_id, "tag": tag})

        return True, "valid", sanitized_list


def _parse_ai_annotation_response(response_text: str, unit_ids: List[str]) -> Any:
    """Decode a JSON array without merging examples and output into one array."""
    decoder = json.JSONDecoder()
    candidates = []
    expected = set(unit_ids)
    for match in re.finditer(r"\[", response_text):
        try:
            value, _ = decoder.raw_decode(response_text[match.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, list):
            continue
        candidates.append(value)
        # Models may include an example array before the actual answer.
        # Selecting the expected units still leaves tag/schema validation intact.
        if all(isinstance(item, dict) and isinstance(item.get("unit"), str) for item in value):
            if {item["unit"] for item in value} == expected:
                return value
    if candidates:
        return candidates[-1]
    raise ValueError("No valid JSON array returned by AI")


def generate_ai_html(
    job_id: str,
    files_dir: str = "files",
    llm_client: Optional[Any] = None,
    progress_callback: Optional[Any] = None,
    cancel_requested: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Generate ai.html; retain basic HTML if AI fails or is cancelled."""
    def check_cancelled():
        if cancel_requested and cancel_requested():
            raise InterruptedError("AI HTML export cancelled by user")

    def report(stage, **details):
        check_cancelled()
        if progress_callback:
            progress_callback(stage=stage, **details)

    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    export_dir = os.path.join(job_dir, "export")
    basic_path = os.path.join(export_dir, "basic.html")

    # Ensure basic.html exists first
    if not os.path.exists(basic_path):
        generate_basic_html(job_id, files_dir=files_dir)

    with open(basic_path, "r", encoding="utf-8") as f:
        basic_html_content = f.read()

    # Extract all elements that can be annotated
    unit_pattern = re.compile(r'<(p|h1|h2|h3)([^>]*)>(.*?)</\1>', re.DOTALL)
    matches = list(unit_pattern.finditer(basic_html_content))

    src_rev = compute_source_revision(job_dir)
    model_attr = getattr(llm_client, "model", None)
    if not isinstance(model_attr, str):
        model_attr = getattr(llm_client, "model_name", None)
    model_name = model_attr if isinstance(model_attr, str) else ("google/gemma-3-1b" if llm_client else "none")
    prompt_version = "v1.0"
    temperature = 0.0
    generated_at = datetime.now(timezone.utc).isoformat()
    chunk_count = 0

    if not matches:
        meta = {
            "mode": "ai",
            "model": model_name,
            "prompt_version": prompt_version,
            "temperature": temperature,
            "generated_at": generated_at,
            "chunk_count": 0,
            "validator_status": "no_units",
            "source_revision": src_rev,
        }
        return basic_html_content, meta

    units_data = []
    for idx, m in enumerate(matches):
        u_id = f"u{idx}"
        tag = m.group(1)
        raw_text = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        units_data.append({
            "unit": u_id,
            "text": raw_text[:120],
            "deterministic_tag": tag,
        })
    # Limit both unit count and UTF-8 bytes. Byte count is a conservative
    # upper bound for byte-based tokenizers, including Thai and JSON overhead.
    # 5,500 prompt bytes + 1,600 output tokens leaves room within 8,192 tokens.
    prompt_rules = (
        "Classify Thai OCR units as p, h1, h2, or h3. Return ONLY valid JSON.\n"
        "Return exactly one object per supplied unit, in the same order, with "
        'keys "unit" and "tag", e.g. [{"unit":"u0","tag":"p"}].\n'
        "Do not change, translate, or summarize text. Existing table/list markup is immutable and must remain unchanged. Body text uses p.\n"
        "At most one h1 across the whole document, only a main title in the first batch.\n"
        "Do not skip heading levels. Respect heading context from previous batches.\n"
    )

    def batch_prompt(batch, heading_context):
        return (prompt_rules + heading_context + "\nUnits to classify:\n"
                + json.dumps(batch, ensure_ascii=False, separators=(",", ":")))

    # Reserve space for heading context while planning the batches.
    context_reserve = "h1 already used: true. Last heading level: h3. This is not the first batch."
    batches = []
    batch = []
    for unit in units_data:
        candidate = batch + [unit]
        if batch and (len(candidate) > 25
                      or len(batch_prompt(candidate, context_reserve).encode("utf-8")) > 5500):
            batches.append(batch)
            batch = []
        batch.append(unit)
    if batch:
        batches.append(batch)
    chunk_count = len(batches)
    completed_chunks = 0
    chunk_index = 0

    def metadata(status, **details):
        return {
            "mode": "ai", "model": model_name, "prompt_version": "v1.1-batched",
            "temperature": temperature, "generated_at": generated_at,
            "chunk_count": chunk_count, "completed_chunks": completed_chunks,
            "validator_status": status, "source_revision": src_rev, **details,
        }

    if llm_client is None:
        meta = metadata("locked_ai_offline", message="Local AI is offline or not configured")
        _update_export_meta(job_dir, "ai", meta)
        return basic_html_content, meta

    try:
        report("processing", chunk_count=chunk_count, completed_chunks=0, current_chunk=0)
        clean_annotations = []
        h1_used = False
        last_heading = 0
        for chunk_index, batch in enumerate(batches, 1):
            report("waiting_ai", chunk_count=chunk_count, completed_chunks=completed_chunks,
                   current_chunk=chunk_index)
            heading_context = (
                f"h1 already used: {str(h1_used).lower()}. "
                f"Last heading level: h{last_heading}. "
                + ("This is the first batch." if chunk_index == 1 else "This is not the first batch.")
            )
            prompt = batch_prompt(batch, heading_context)
            if callable(getattr(type(llm_client), "generate_html_annotations", None)):
                response_text = llm_client.generate_html_annotations(prompt=prompt, max_tokens=1600, temperature=0.0)
            elif hasattr(llm_client, "generate"):
                response_text = llm_client.generate(prompt=prompt, max_tokens=1600, temperature=0.0)
            elif hasattr(llm_client, "chat_completion"):
                res = llm_client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1600, temperature=0.0,
                )
                if not res.get("success"):
                    raise RuntimeError(res.get("error") or "LLM chat completion failed")
                response_text = res.get("content", "")
            else:
                raise AttributeError("LLM client does not provide generate or chat_completion")
            check_cancelled()
            unit_ids = [u["unit"] for u in batch]
            raw_annotations = _parse_ai_annotation_response(response_text, unit_ids)
            valid, reason, annotations = AIAnnotationValidator(unit_ids).validate(raw_annotations)
            if valid and {a["unit"] for a in annotations} != set(unit_ids):
                valid, reason = False, "AI did not annotate every unit in the batch"
            if not valid:
                meta = metadata("rejected", validator_reason=reason, failed_chunk=chunk_index)
                _update_export_meta(job_dir, "ai", meta)
                return basic_html_content, meta
            # Validate in document order, independent of AI response ordering.
            by_unit = {a["unit"]: a for a in annotations}
            clean_annotations.extend(by_unit[uid] for uid in unit_ids)
            completed_chunks += 1
            report("processing", chunk_count=chunk_count, completed_chunks=completed_chunks,
                   current_chunk=chunk_index)
            for uid in unit_ids:
                tag = by_unit[uid]["tag"]
                if tag.startswith("h"):
                    last_heading = int(tag[1])
                    h1_used = h1_used or tag == "h1"

        # Per-batch validation cannot catch repeated h1 or heading jumps across
        # boundaries. Validate the entire document before publishing any ai.html.
        report("validating", chunk_count=chunk_count, completed_chunks=completed_chunks,
               current_chunk=chunk_index)
        valid, reason, clean_annotations = AIAnnotationValidator(
            [u["unit"] for u in units_data]
        ).validate(clean_annotations)
        if not valid:
            meta = metadata("rejected", validator_reason=reason)
            _update_export_meta(job_dir, "ai", meta)
            return basic_html_content, meta

        # Apply annotations to basic HTML
        tag_by_unit = {a["unit"]: a["tag"] for a in clean_annotations}
        
        # Re-render HTML replacing tags cleanly
        match_indices = {match.start(): idx for idx, match in enumerate(matches)}
        def replacer(match):
            m_idx = match_indices.get(match.start())
            if m_idx is None:
                return match.group(0)
            u_id = f"u{m_idx}"
            new_tag = tag_by_unit.get(u_id, match.group(1))
            attrs = match.group(2)
            content = match.group(3)
            # Add data-src="ai"
            if 'data-src="' in attrs:
                attrs = re.sub(r'data-src="([^"]*)"', r'data-src="\1,ai"', attrs)
            else:
                attrs = f'{attrs} data-src="ai"'
            return f"<{new_tag}{attrs}>{content}</{new_tag}>"

        ai_html_content = unit_pattern.sub(replacer, basic_html_content)
        ai_path = os.path.join(export_dir, "ai.html")
        report("publishing", chunk_count=chunk_count, completed_chunks=completed_chunks,
               current_chunk=chunk_index)
        atomic_write_text(ai_path, ai_html_content)

        meta = metadata(
            "passed", annotations_applied=len(clean_annotations),
            hash=hashlib.sha256(ai_html_content.encode("utf-8")).hexdigest(),
        )
        _update_export_meta(job_dir, "ai", meta)
        return ai_html_content, meta

    except InterruptedError as e:
        meta = metadata("cancelled", error=str(e), failed_chunk=chunk_index)
        _update_export_meta(job_dir, "ai", meta)
        return basic_html_content, meta
    except Exception as e:
        meta = metadata("error", error=str(e), failed_chunk=chunk_index)
        _update_export_meta(job_dir, "ai", meta)
        return basic_html_content, meta



class StrictHtmlSanitizer(HTMLParser):
    ALLOWED_TAGS = {"p", "h1", "h2", "h3", "b", "i", "strong", "em", "u", "s", "span", "br", "section", "main", "div", "ul", "ol", "li", "a", "blockquote", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption"}
    ALLOWED_ATTRS = {"id", "class", "data-page", "data-src", "data-edited", "lang", "rowspan", "colspan"}
    # Tags that have closing tags and whose inner text must be completely discarded
    DISCARD_CONTENT_TAGS = {"head", "title", "script", "style", "iframe", "object", "svg", "math", "applet", "form", "button", "textarea", "select"}
    # Void/self-closing tags that must simply be dropped without affecting discard depth
    VOID_FORBIDDEN_TAGS = {"embed", "link", "base", "input", "img", "param", "source", "track", "wbr", "frame"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self.discard_depth = 0

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.VOID_FORBIDDEN_TAGS:
            return
        if tag_lower in self.DISCARD_CONTENT_TAGS:
            self.discard_depth += 1
            return
        if self.discard_depth > 0:
            return
        if tag_lower not in self.ALLOWED_TAGS:
            return

        clean_attrs = []
        for name, value in attrs:
            name_lower = name.lower()
            if tag_lower == "a" and name_lower == "href" and value:
                from urllib.parse import urlsplit
                href = value.strip()
                if not re.search(r"[\x00-\x20\x7f]", href):
                    try:
                        parts = urlsplit(href)
                        if href.startswith("#") or (parts.scheme in {"http", "https"} and parts.netloc) or (parts.scheme == "mailto" and parts.path):
                            clean_attrs.append(("href", href))
                    except ValueError:
                        pass
                continue
            if name_lower in {"rowspan", "colspan"}:
                if tag_lower in {"th", "td"} and value and value.isdigit() and 1 <= int(value) <= 1000:
                    clean_attrs.append((name_lower, str(int(value))))
                continue
            if name_lower not in self.ALLOWED_ATTRS:
                continue
            if name_lower.startswith("on") or ":" in name_lower:
                continue
            if value is not None:
                val_lower = value.lower()
                if "javascript:" in val_lower or "vbscript:" in val_lower or "data:" in val_lower or "url(" in val_lower or "@import" in val_lower:
                    continue
                clean_attrs.append((name_lower, value))

        attr_str = ""
        if clean_attrs:
            attr_parts = [f'{n}="{html.escape(v, quote=True)}"' for n, v in clean_attrs]
            attr_str = " " + " ".join(attr_parts)

        if tag_lower == "br":
            self.output.append(f"<br{attr_str}>")
        else:
            self.output.append(f"<{tag_lower}{attr_str}>")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.DISCARD_CONTENT_TAGS:
            if self.discard_depth > 0:
                self.discard_depth -= 1
            return
        if self.discard_depth > 0:
            return
        if tag_lower in self.ALLOWED_TAGS and tag_lower != "br":
            self.output.append(f"</{tag_lower}>")

    def handle_data(self, data):
        if self.discard_depth > 0:
            return
        self.output.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self.discard_depth > 0:
            return
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        if self.discard_depth > 0:
            return
        self.output.append(f"&#{name};")

    def get_sanitized(self) -> str:
        return "".join(self.output)


def sanitize_final_html(raw_html: str, title: str = "OCR Document") -> str:
    """
    Sanitizes user-edited final HTML using HTMLParser and a strict allowlist.
    Discards dangerous tags (<script>, <style>, <iframe>, <object>, <embed>, <form>, etc.),
    drops event handlers (on*), style attributes, and unsafe link protocols.
    Embeds sanitized content into canonical document shell with strict CSP and offline system CSS.
    """
    sanitizer = StrictHtmlSanitizer()
    sanitizer.feed(raw_html or "")
    sanitizer.close()
    body_content = sanitizer.get_sanitized()
    return get_html_document_shell(title=title, body_content=body_content)


def save_final_html(
    job_id: str,
    final_html_content: str,
    base_revision: Optional[str] = None,
    overwrite: bool = False,
    files_dir: str = "files",
) -> Dict[str, Any]:
    """
    Saves user-edited final.html.
    Checks revision to detect conflicts (409 unless overwrite=True).
    Sanitizes HTML content with HTMLParser and strict allowlist.
    """
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    export_dir = os.path.join(job_dir, "export")
    os.makedirs(export_dir, exist_ok=True)
    final_path = os.path.join(export_dir, "final.html")

    current_src_rev = compute_source_revision(job_dir)
    if base_revision and base_revision != current_src_rev and not overwrite:
        raise ValueError("Conflict: source_revision has changed since this edit was started.")

    # Sanitize final HTML using HTMLParser and strict allowlist
    sanitized = sanitize_final_html(final_html_content, title=f"OCR Document - {job_id}")

    atomic_write_text(final_path, sanitized)

    meta = {
        "mode": "final",
        "saved_at": current_src_rev,
        "hash": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
    }
    _update_export_meta(job_dir, "final", meta)
    return meta


def _update_export_meta(job_dir: str, variant: str, data: Dict[str, Any]) -> None:
    """Atomically updates export_meta.json inside files/{job_id}/export/."""
    export_dir = os.path.join(job_dir, "export")
    os.makedirs(export_dir, exist_ok=True)
    meta_path = os.path.join(export_dir, "export_meta.json")

    meta: Dict[str, Any] = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}

    current_rev = compute_source_revision(job_dir)
    if meta.get(variant) == data and meta.get("current_source_revision") == current_rev:
        return

    meta[variant] = data
    meta["job_id"] = os.path.basename(job_dir)
    meta["current_source_revision"] = current_rev
    atomic_write_json(meta_path, meta)


def get_export_status(job_id: str, files_dir: str = "files") -> Dict[str, Any]:
    """Retrieves current export status and stale flag."""
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    export_dir = os.path.join(job_dir, "export")
    meta_path = os.path.join(export_dir, "export_meta.json")

    current_src_rev = compute_source_revision(job_dir)

    if not os.path.exists(meta_path):
        return {
            "job_id": job_id,
            "status": "not_generated",
            "source_revision": current_src_rev,
            "has_basic": False,
            "has_ai": False,
            "has_final": False,
            "variants": [],
            "is_stale": False,
        }

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}

    has_basic = os.path.exists(os.path.join(export_dir, "basic.html"))
    has_ai = os.path.exists(os.path.join(export_dir, "ai.html"))
    has_final = os.path.exists(os.path.join(export_dir, "final.html"))

    # Stale detection: if current_source_revision does not match the revision when basic was generated
    basic_rev = meta.get("basic", {}).get("source_revision")
    is_stale = bool(basic_rev and basic_rev != current_src_rev)

    variants = []
    if has_basic:
        variants.append("basic")
    if has_ai:
        variants.append("ai")
    if has_final:
        variants.append("final")

    return {
        "job_id": job_id,
        "status": "ready" if variants else "not_generated",
        "source_revision": current_src_rev,
        "is_stale": is_stale,
        "has_basic": has_basic,
        "has_ai": has_ai,
        "has_final": has_final,
        "variants": variants,
        "metadata": meta,
    }
