"""Deterministic document translation model, glossary and structural validator."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.cleanup_service import safe_job_dir
from src.file_utils import atomic_write_json, atomic_write_text
from src.html_exporter import sanitize_final_html

SCHEMA_VERSION = "10.0"
PROMPT_VERSION = "10.0.0"
ASSEMBLER_VERSION = "10.2.0"
VALIDATOR_VERSION = "10.4.1"
STYLES = {"general", "novel", "academic", "official"}
PROVIDERS = {
    "local", "local_api", "cli_codex", "cli_gemini", "cli_agy", "cli_claude", "cli_lms",
    "google", "hybrid",
}
SOURCE_VARIANTS = {
    "auto", "final", "structured", "ai", "basic",
    "text_final", "text_corrected", "text_raw",
}
MAX_SEGMENTS = 50_000
MAX_TEXT_BYTES = 20 * 1024 * 1024

STYLE_RULES = {
    "general": "แปลให้ชัดเจน เป็นธรรมชาติ ไม่เพิ่ม ตัด หรือสรุปข้อมูล",
    "novel": "รักษาน้ำเสียง ผู้พูด บทสนทนา มุมมอง ความต่อเนื่อง และชื่อเฉพาะ ห้ามแต่งเหตุการณ์เพิ่ม",
    "academic": "รักษาศัพท์เทคนิค สูตร citation footnote หน่วย code และระดับภาษาทางวิชาการ",
    "official": "ใช้ภาษาทางการ รักษาชื่อตำแหน่ง เลขหนังสือ วันที่ ข้อกฎหมาย และรูปแบบรายการ",
}
COMMON_RULE = ("ไม่ต้องพยายามแปลทุกคำ ศัพท์เฉพาะ ชื่อเทคโนโลยี ชื่อผลิตภัณฑ์ และตัวย่อ "
               "ให้คงเดิมหรือทับศัพท์ตาม glossary/context เมื่อการแปลทำให้ความหมายคลาดเคลื่อน")

CRITICAL_PATTERNS = {
    "number": r"(?<![A-Za-z0-9_])[-+]?\d(?:\d|,(?=\d))*(?:\.\d+)?%?(?![A-Za-z0-9_])",
    "date": r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b",
    "time": r"\b\d{1,2}:\d{2}(?::\d{2})?\b",
    "money": r"(?:[$€£฿¥]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|THB|EUR|GBP|CNY))",
    "url": r"https?://[^\s<]+",
    "email": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    "citation": r"(?:\[[0-9,\- ]+\]|\([A-Z][A-Za-z-]+,?\s+\d{4}[a-z]?\))",
    "unit": r"(?<![A-Za-z])\d+(?:\.\d+)?\s?(?:mm|cm|m|km|mg|g|kg|ml|L|°C|°F|kWh|MB|GB|GHz)\b",
    "code": r"`[^`]+`|\b(?:[A-Za-z_][A-Za-z0-9_]*\([^\n)]*\)|[A-Za-z_][A-Za-z0-9_]{1,}\.[A-Za-z_][A-Za-z0-9_]{1,})",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any, length: int = 24) -> str:
    raw = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def translation_dir(files_dir: str, job_id: str) -> str:
    return os.path.join(safe_job_dir(files_dir, job_id), "export", "translation")


def read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def normalize_language(value: str, allow_auto: bool = False) -> str:
    language = str(value or "").strip()
    if allow_auto and language == "auto":
        return language
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        raise ValueError("Language must be a BCP-47 code")
    parts = language.split("-")
    return "-".join([parts[0].lower()] + [part.upper() if len(part) == 2 else part for part in parts[1:]])


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    source_language = normalize_language(config.get("source_language", "auto"), allow_auto=True)
    target_language = normalize_language(config.get("target_language", ""))
    if source_language != "auto" and source_language.lower() == target_language.lower():
        raise ValueError("Source and target language must be different")
    raw_style = str(config.get("style", "general")).strip().lower()
    style = {"ทั่วไป": "general", "นิยาย": "novel", "วิชาการ": "academic", "ราชการ": "official"}.get(raw_style, raw_style)
    provider = str(config.get("provider", "local")).lower()
    source_variant = str(config.get("source_variant", "auto")).lower()
    if style not in STYLES:
        raise ValueError("Unsupported translation style")
    if provider not in PROVIDERS:
        raise ValueError("Unsupported translation provider")
    if source_variant not in SOURCE_VARIANTS:
        raise ValueError("Unsupported source artifact")
    manual_strategy = str(config.get("manual_strategy", "preserve")).lower()
    if manual_strategy not in {"preserve", "rebase", "reset"}:
        raise ValueError("Unsupported manual-final strategy")
    return {
        "source_language": source_language,
        "target_language": target_language,
        "style": style,
        "provider": provider,
        "source_variant": source_variant,
        "model": str(config.get("model") or "").strip()[:200],
        "translate_toc": bool(config.get("translate_toc", True)),
        "cloud_consent": bool(config.get("cloud_consent", False)),
        "manual_strategy": manual_strategy,
        "preserve_manual_final": manual_strategy != "reset" and bool(config.get("preserve_manual_final", True)),
    }


def _term_matches_language(value: str, language: Optional[str]) -> bool:
    if not language or language == "auto" or len(value.strip()) < 4:
        return True
    base = language.split("-", 1)[0].lower()
    patterns = {"th":r"[\u0E00-\u0E7F]","zh":r"[\u3400-\u9FFF]","ja":r"[\u3040-\u30FF\u3400-\u9FFF]","ko":r"[\uAC00-\uD7AF]"}
    if base in patterns:
        return bool(re.search(patterns[base], value))
    if base in {"en","de","fr","es","vi","id","ms"}:
        return bool(re.search(r"[A-Za-zÀ-ỹ]", value))
    return True


def validate_glossary(entries: Iterable[Dict[str, Any]], source_language: Optional[str] = None,
                      target_language: Optional[str] = None) -> List[Dict[str, Any]]:
    clean, seen = [], set()
    for raw in entries or []:
        source = str(raw.get("source", "")).strip()
        target = str(raw.get("target", "")).strip()
        preserve = bool(raw.get("do_not_translate", False))
        raw_mode = str(raw.get("mode") or ("preserved" if preserve else "translated")).lower()
        mode = {"translate":"translated","preserve":"preserved","transliterate":"transliterated"}.get(raw_mode,raw_mode)
        case_sensitive = bool(raw.get("case_sensitive", False))
        if not source:
            raise ValueError("Glossary source term must not be empty")
        if not preserve and not target:
            raise ValueError(f"Glossary target for '{source}' must not be empty")
        if mode not in {"translated", "preserved", "transliterated"}:
            raise ValueError(f"Unsupported glossary mode: {mode}")
        if preserve and mode != "preserved":
            raise ValueError("Do-not-translate term must use preserve mode")
        if not _term_matches_language(source, source_language):
            raise ValueError(f"Glossary source language mismatch: {source}")
        if not preserve and not _term_matches_language(target, target_language):
            raise ValueError(f"Glossary target language mismatch: {target}")
        key = source if case_sensitive else source.casefold()
        if key in seen:
            raise ValueError(f"Duplicate glossary term: {source}")
        seen.add(key)
        clean.append({"source": source[:300], "target": target[:300],
                      "case_sensitive": case_sensitive, "do_not_translate": preserve, "mode": mode})
    return clean


def save_glossary(files_dir: str, job_id: str, entries: Iterable[Dict[str, Any]],
                  base_revision: Optional[str] = None, source_language: Optional[str] = None,
                  target_language: Optional[str] = None) -> Dict[str, Any]:
    directory = translation_dir(files_dir, job_id)
    path = os.path.join(directory, "glossary.json")
    previous = read_json(path)
    if base_revision is not None and previous.get("revision") not in {None, base_revision}:
        raise ValueError("Conflict: glossary revision changed")
    clean = validate_glossary(entries, source_language, target_language)
    revision = digest(clean)
    model = {"schema_version": SCHEMA_VERSION, "entries": clean, "revision": revision, "updated_at": utc_now()}
    atomic_write_json(path, model)
    return model


def load_glossary(files_dir: str, job_id: str) -> Dict[str, Any]:
    model = read_json(os.path.join(translation_dir(files_dir, job_id), "glossary.json"))
    return model or {"schema_version": SCHEMA_VERSION, "entries": [], "revision": digest([]), "updated_at": None}


def resolve_source(files_dir: str, job_id: str, variant: str) -> Tuple[str, str, str]:
    job_dir = safe_job_dir(files_dir, job_id)
    export_dir = os.path.join(job_dir, "export")
    requested = str(variant or "auto").lower()
    candidates = ([requested] if requested != "auto" else
                  ["final", "structured", "ai", "basic", "text_final", "text_corrected", "text_raw"])
    for candidate in candidates:
        if candidate.startswith("text_"):
            path = os.path.join(job_dir, f"{candidate.removeprefix('text_')}.txt")
        else:
            path = (os.path.join(export_dir, "structured", "structured.html") if candidate == "structured"
                    else os.path.join(export_dir, f"{candidate}.html"))
        if os.path.isfile(path):
            with open(path, "rb") as stream:
                content = stream.read(MAX_TEXT_BYTES + 1)
            if len(content) > MAX_TEXT_BYTES:
                raise ValueError("Translation source exceeds 20 MB")
            return candidate, path, hashlib.sha256(content).hexdigest()[:24]
    raise FileNotFoundError("No saved HTML or text artifact is available for translation")


def text_source_to_html(source_text: str) -> str:
    """Wrap plain OCR text in stable HTML blocks for the existing segment pipeline."""
    sections = []
    for page_number, page_text in enumerate(source_text.split("\f"), 1):
        paragraphs = re.split(r"(?:\r?\n){2,}", page_text)
        blocks = []
        for paragraph_number, paragraph in enumerate(paragraphs, 1):
            if not paragraph.strip():
                continue
            block_id = f"text-p{page_number}-{paragraph_number}"
            blocks.append(
                f'<p data-block-id="{block_id}" data-page="{page_number}">'
                f'{html.escape(paragraph)}</p>'
            )
        sections.append(f'<section data-page="{page_number}">{"".join(blocks)}</section>')
    return '<!doctype html><html><head><meta charset="utf-8"></head><body>' + "".join(sections) + '</body></html>'


class SegmentParser(HTMLParser):
    """Parse saved HTML into immutable markup tokens and stable text segments."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens: List[Dict[str, Any]] = []
        self.segments: List[Dict[str, Any]] = []
        self.stack: List[Dict[str, Any]] = []
        self.counts: Dict[str, int] = {}
        self.row_count = 0
        self.in_body = False

    def handle_decl(self, decl): self.tokens.append({"kind": "raw", "value": f"<!{decl}>"})
    def handle_comment(self, data): pass

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if tag == "tr":
            self.row_count += 1
            attr_map["_translation_row_group"] = f"row-{self.row_count}"
        self.stack.append({"tag": tag, "attrs": attr_map})
        if tag == "body": self.in_body = True
        rendered = "".join(f' {name}="{html.escape(str(value or ""), quote=True)}"' for name, value in attrs)
        self.tokens.append({"kind": "raw", "value": f"<{tag}{rendered}>"})

    def handle_startendtag(self, tag, attrs):
        rendered = "".join(f' {name}="{html.escape(str(value or ""), quote=True)}"' for name, value in attrs)
        self.tokens.append({"kind": "raw", "value": f"<{tag}{rendered} />"})

    def handle_endtag(self, tag):
        self.tokens.append({"kind": "raw", "value": f"</{tag}>"})
        if tag == "body": self.in_body = False
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if not self.in_body or not data.strip() or not self.stack:
            self.tokens.append({"kind": "raw", "value": data})
            return
        current = self.stack[-1]
        tag = current["tag"]
        if tag in {"style", "script"}:
            self.tokens.append({"kind": "raw", "value": data})
            return
        anchor = None
        page = None
        group_id = None
        bbox = None
        for item in reversed(self.stack):
            attrs = item["attrs"]
            anchor = anchor or attrs.get("data-cell-id") or attrs.get("data-block-id") or attrs.get("id") or attrs.get("data-src")
            page = page or attrs.get("data-page")
            group_id = group_id or attrs.get("_translation_row_group")
            if bbox is None and "data-bbox" in attrs:
                raw_bbox = attrs["data-bbox"]
                try:
                    bbox = json.loads(raw_bbox) if isinstance(raw_bbox, str) else raw_bbox
                except Exception:
                    bbox = raw_bbox
        base = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(anchor or tag)).strip("-") or tag
        self.counts[base] = self.counts.get(base, 0) + 1
        segment_id = f"seg-{base}-{self.counts[base]}"
        leading = data[:len(data) - len(data.lstrip())]
        trailing = data[len(data.rstrip()):]
        source = data.strip()
        table_cell = next((item for item in reversed(self.stack) if item["tag"] in {"td", "th"}), None)
        missing_cell_model = bool(table_cell and not (
            table_cell["attrs"].get("data-cell-id") or table_cell["attrs"].get("id")
        ))
        preserve = tag in {"code", "pre"} or looks_like_code(source) or missing_cell_model
        segment = {
            "id": segment_id, "type": tag, "page": page, "group_id": group_id, "bbox": bbox, "source_text": source,
            "baseline_text": None, "translated_text": source if preserve else None,
            "final_text": source if preserve else None,
            "warnings": ["table_cell_model_missing"] if missing_cell_model else [],
            "status": "unresolved" if missing_cell_model else "preserved" if preserve else "pending",
            "provenance": {"provider": "source", "model": None, "prompt_version": PROMPT_VERSION},
            "term_states": [], "manual_edited": False,
        }
        self.segments.append(segment)
        self.tokens.append({"kind": "segment", "id": segment_id, "leading": leading, "trailing": trailing})


def looks_like_code(text: str) -> bool:
    stripped=text.strip()
    if re.match(r"^\s{2,}\S",text): return True
    if re.match(r"^(?:def|class)\s+[A-Za-z_]\w*",stripped): return True
    if re.match(r"^function\s+[A-Za-z_]\w*\s*\(",stripped): return True
    if re.match(r"^(?:const|let|var)\s+[A-Za-z_]\w*\s*=",stripped): return True
    if re.match(r"^(?:import\s+|#include\b|</?[A-Za-z][^>]*>)",stripped): return True
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\([^\n)]*\);?",stripped): return True
    return bool("=>" in stripped or ("{" in stripped and ("}" in stripped or stripped.endswith(";"))))


def extract_document(source_html: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    parser = SegmentParser()
    parser.feed(source_html)
    parser.close()
    if len(parser.segments) > MAX_SEGMENTS:
        raise ValueError("Translation source has too many segments")
    return parser.tokens, parser.segments


def detect_language(segments: List[Dict[str, Any]]) -> Tuple[str, float, Optional[str]]:
    text = " ".join(segment["source_text"] for segment in segments)[:100_000]
    counts = {"th":len(re.findall(r"[\u0E00-\u0E7F]",text)),"zh":len(re.findall(r"[\u3400-\u9FFF]",text)),
              "en":len(re.findall(r"[A-Za-z]",text))}
    total=sum(counts.values())
    if not total: return "und",0.0,"ไม่พบอักษรเพียงพอสำหรับตรวจภาษา"
    detected=max(counts,key=counts.get); confidence=counts[detected]/total
    warning="พบข้อความหลายภาษา โปรดตรวจภาษาต้นทาง" if confidence<0.8 else None
    return detected,round(confidence,4),warning


def batch_segments(segments: List[Dict[str, Any]], max_codepoints: int = 5000,
                   max_segments: int = 8) -> List[List[Dict[str, Any]]]:
    batches, current, size, pending_group = [], [], 0, []
    def flush_group(group):
        nonlocal current,size
        group_size=sum(len(item.get("source_text", "")) for item in group)
        if current and (size+group_size>max_codepoints or len(current)+len(group)>max_segments):
            batches.append(current);current=[];size=0
        current.extend(group);size+=group_size
    for segment in segments:
        if segment.get("status") in {"preserved", "unresolved"}:
            continue
        group_key=segment.get("translation_unit_id") or segment.get("group_id")
        if group_key:
            pending_key=pending_group[-1].get("translation_unit_id") or pending_group[-1].get("group_id") if pending_group else None
            if pending_group and pending_key!=group_key:
                flush_group(pending_group);pending_group=[]
            pending_group.append(segment);continue
        if pending_group: flush_group(pending_group);pending_group=[]
        flush_group([segment])
    if pending_group: flush_group(pending_group)
    if current: batches.append(current)
    return batches


INTENTIONAL_HYPHEN_PREFIXES = {
    "self", "well", "co", "cross", "ex", "all", "half", "quasi", "step", "great",
    "user", "state", "cost", "real", "high", "low", "open", "end", "peer"
}


def analyze_dehyphenation(before_text: str, after_text: str) -> Dict[str, Any]:
    """Analyze English line-break hyphenation with strict preservation rules."""
    # Check soft hyphen U+00AD
    if before_text.endswith("\u00ad"):
        clean_before = before_text[:-1]
        return {
            "should_dehyphenate": True,
            "combined_separator": "",
            "kind": "soft_hyphen",
            "rule": "soft_hyphen_merge",
            "warning": None,
            "before_part": clean_before,
            "after_part": after_text,
        }
    
    if not before_text.endswith("-"):
        return {
            "should_dehyphenate": False,
            "combined_separator": " ",
            "kind": "space_continuation",
            "rule": "line_continuation",
            "warning": None,
            "before_part": before_text,
            "after_part": after_text,
        }
    
    # Hyphen at end of before_text
    # 1. Minus sign / spacing check: e.g. "x -", " --"
    if before_text.endswith(" -") or before_text.endswith(" --"):
        return {
            "should_dehyphenate": False,
            "combined_separator": " ",
            "kind": "minus_sign",
            "rule": "minus_sign_preserve",
            "warning": None,
            "before_part": before_text,
            "after_part": after_text,
        }
    
    # 2. Check URLs, emails, citations, code, identifiers
    if (re.search(r"https?://|\S+@\S+", before_text) or
        re.search(r"https?://|\S+@\S+", after_text) or
        looks_like_code(before_text) or looks_like_code(after_text) or
        re.search(r"[`_]|\b[A-Za-z0-9]+_[A-Za-z0-9]+\b", before_text) or
        re.search(r"\[\d+\]|\(\w+,\s*\d{4}\)", before_text)):
        return {
            "should_dehyphenate": False,
            "combined_separator": "",
            "kind": "code_or_identifier",
            "rule": "code_or_identifier_preserve",
            "warning": "intentional_hyphen_code_url_preserved",
            "before_part": before_text,
            "after_part": after_text,
        }
    
    # 3. Extract word fragment before '-' and word fragment after
    prefix_match = re.search(r"([A-Za-z]+)-$", before_text)
    suffix_match = re.match(r"^([A-Za-z]+)", after_text)
    if not prefix_match or not suffix_match:
        return {
            "should_dehyphenate": False,
            "combined_separator": "",
            "kind": "non_alpha",
            "rule": "non_alpha_hyphen_preserve",
            "warning": None,
            "before_part": before_text,
            "after_part": after_text,
        }
    
    prefix = prefix_match.group(1)
    suffix = suffix_match.group(1)
    
    # 4. Next line starts with uppercase letter (proper noun or sentence boundary)
    if suffix[0].isupper():
        return {
            "should_dehyphenate": False,
            "combined_separator": " ",
            "kind": "capitalized_suffix",
            "rule": "capitalized_suffix_preserve",
            "warning": "hyphen_followed_by_capital_word",
            "before_part": before_text,
            "after_part": after_text,
        }
    
    # 5. Compound word check:
    if prefix.lower() in INTENTIONAL_HYPHEN_PREFIXES:
        return {
            "should_dehyphenate": False,
            "combined_separator": "",
            "kind": "compound_word",
            "rule": "compound_word_preserve",
            "warning": f"compound_hyphen_preserved: {prefix}-{suffix}",
            "before_part": before_text,
            "after_part": after_text,
        }
    
    # 6. Standard end-of-line hyphenation for split word (e.g. lay- + ers -> layers)
    return {
        "should_dehyphenate": True,
        "combined_separator": "",
        "kind": "dehyphenate",
        "rule": "eol_split_word_merge",
        "warning": None,
        "before_part": before_text[:-1],
        "after_part": after_text,
    }


def _assembly_block_key(segment: Dict[str, Any]) -> Optional[str]:
    """Return an OCR line-series key without crossing semantic HTML boundaries."""
    if segment.get("type") != "p" or segment.get("group_id") or segment.get("status") in {"preserved", "unresolved"}:
        return None
    match = re.match(r"^(.*)_l\d+-\d+$", str(segment.get("id", "")))
    return match.group(1) if match else None


def assemble_translation_units(segments: List[Dict[str, Any]], *, max_members: int = 8,
                               max_codepoints: int = 3500) -> List[Dict[str, Any]]:
    """Attach reversible paragraph context to OCR line segments before translation.

    Each original segment remains the review/export authority. A unit adds
    adjacent-line context, including a de-hyphenated reading form, so a provider
    returns coherent translations without altering document structure.
    """
    units: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    key: Optional[tuple[Any, Any]] = None

    def flush() -> None:
        nonlocal current, key
        if not current:
            return
        spans: List[Dict[str, Any]] = []
        transformations: List[Dict[str, Any]] = []
        warnings: List[str] = []
        original_texts: List[str] = []
        bboxes: List[Dict[str, Any]] = []
        text = ""

        for index, segment in enumerate(current):
            source = str(segment["source_text"])
            original_texts.append(source)
            if segment.get("bbox"):
                bboxes.append({"segment_id": segment["id"], "bbox": segment["bbox"]})

            if index == 0:
                start = 0
                text = source
                spans.append({"segment_id": segment["id"], "start": start, "end": len(text)})
                continue

            analysis = analyze_dehyphenation(text, source)
            before_seg = current[index - 1]
            if analysis["should_dehyphenate"]:
                text = analysis["before_part"] + analysis["combined_separator"]
                transformations.append({
                    "kind": analysis["kind"],
                    "rule": analysis["rule"],
                    "before_id": before_seg["id"],
                    "after_id": segment["id"],
                    "original": f"{before_seg['source_text']} {source}",
                    "result": text + source,
                })
            else:
                sep = analysis["combined_separator"]
                text += sep
                if analysis.get("kind") not in {"space_continuation", "none"}:
                    transformations.append({
                        "kind": analysis["kind"],
                        "rule": analysis["rule"],
                        "before_id": before_seg["id"],
                        "after_id": segment["id"],
                        "original": f"{before_seg['source_text']} {source}",
                        "result": text + source,
                    })

            if analysis.get("warning"):
                warnings.append(analysis["warning"])

            start = len(text)
            text += source
            spans.append({"segment_id": segment["id"], "start": start, "end": len(text)})

        unit_id = f"tu-{current[0]['id']}"
        member_ids = [segment["id"] for segment in current]
        unit = {
            "id": unit_id,
            "assembler_version": ASSEMBLER_VERSION,
            "source_segment_ids": member_ids,
            "member_ids": member_ids,
            "page": current[0].get("page"),
            "bboxes": bboxes,
            "original_text": "\n".join(original_texts),
            "assembled_text": text,
            "text": text,
            "spans": spans,
            "char_spans": spans,
            "transformations": transformations,
            "warnings": warnings,
            "enabled": True,
        }
        units.append(unit)
        span_by_id = {span["segment_id"]: span for span in spans}
        for index, segment in enumerate(current):
            segment.update(
                translation_unit_id=unit_id,
                translation_unit_member_ids=member_ids,
                translation_unit_member_index=index,
                translation_unit_text=text,
                translation_unit_source_span=span_by_id[segment["id"]],
                translation_unit_enabled=True,
            )
        current = []
        key = None

    for segment in segments:
        block = _assembly_block_key(segment)
        candidate_key = (segment.get("page"), block)
        candidate_size = sum(len(str(item["source_text"])) for item in current) + len(str(segment["source_text"]))
        if not block or (current and (candidate_key != key or len(current) >= max_members or candidate_size > max_codepoints)):
            flush()
        if not block:
            continue
        current.append(segment)
        key = candidate_key
    flush()
    return units


def critical_tokens(text: str) -> Dict[str, List[str]]:
    return {name: re.findall(pattern, text or "", flags=re.I) for name, pattern in CRITICAL_PATTERNS.items()}


def classify_terms(source: str, target: str, glossary: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    states = []
    for entry in glossary:
        flags = 0 if entry["case_sensitive"] else re.I
        if not re.search(re.escape(entry["source"]), source, flags):
            continue
        expected = entry["source"] if entry["do_not_translate"] else entry["target"]
        present = bool(re.search(re.escape(expected), target, flags))
        states.append({"source": entry["source"], "target": expected,
                       "status": entry.get("mode", "preserved" if entry["do_not_translate"] else "translated") if present else "missing"})
    return states


def _target_script_missing(source: str, target: str, target_language: Optional[str]) -> bool:
    """Detect a provider that copied a sentence instead of translating it."""
    if not target_language or looks_like_code(source):
        return False
    source_letters = len(re.findall(r"[A-Za-z\u0E00-\u0E7F\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]", source))
    if source_letters < 12 or len(source.split()) < 3:
        return False
    base = target_language.split("-", 1)[0].lower()
    patterns = {
        "th": r"[\u0E00-\u0E7F]", "zh": r"[\u3400-\u9FFF]",
        "ja": r"[\u3040-\u30FF\u3400-\u9FFF]", "ko": r"[\uAC00-\uD7AF]",
        "en": r"[A-Za-z]", "de": r"[A-Za-zÀ-ÿ]", "fr": r"[A-Za-zÀ-ÿ]",
        "es": r"[A-Za-zÀ-ÿ]", "vi": r"[A-Za-zÀ-ỹ]", "id": r"[A-Za-z]", "ms": r"[A-Za-z]",
    }
    pattern = patterns.get(base)
    return bool(pattern and not re.search(pattern, target))


def validate_translation(source: str, target: str, glossary: List[Dict[str, Any]],
                         target_language: Optional[str] = None) -> List[str]:
    warnings = []
    target_tokens = critical_tokens(target)
    for kind, values in critical_tokens(source).items():
        original, translated = Counter(values), Counter(target_tokens[kind])
        missing = list((original - translated).elements())
        if missing:
            warnings.append(f"critical_{kind}_changed: {', '.join(missing[:5])}")
        added = list((translated - original).elements())
        if added:
            warnings.append(f"critical_{kind}_unexpected: {', '.join(added[:5])}")
    for term in classify_terms(source, target, glossary):
        if term["status"] == "missing": warnings.append(f"glossary_term_changed: {term['source']}")
    if _target_script_missing(source, target, target_language):
        warnings.append("target_language_mismatch")
    return warnings


def segment_output_text(segment: Dict[str, Any]) -> str:
    """Manual final, including an explicit empty edit, is authoritative."""
    if segment.get("final_text") is not None:
        return segment["final_text"]
    if segment.get("translated_text") is not None:
        return segment["translated_text"]
    return segment["source_text"]


def suppress_continuation(segment: Dict[str, Any]) -> bool:
    return bool(segment.get("translation_unit_id") and
                segment.get("translation_unit_member_index", 0) > 0 and
                segment.get("translation_unit_enabled", True) and
                not segment.get("manual_edited") and
                segment_output_text(segment) == "")


def render_html(tokens: List[Dict[str, Any]], segments: List[Dict[str, Any]], title: str = "Translated document") -> str:
    by_id = {segment["id"]: segment for segment in segments}
    output = []
    for token in tokens:
        if token["kind"] == "raw":
            output.append(token["value"])
        else:
            segment = by_id[token["id"]]
            if suppress_continuation(segment):
                # Continuation segment suppressed in reversible assembly
                output.append(token["leading"] + token["trailing"])
            else:
                text = segment_output_text(segment)
                output.append(token["leading"] + html.escape(text, quote=False) + token["trailing"])
    return sanitize_final_html("".join(output), title=title)


def structure_signature(tokens: List[Dict[str, Any]], segments: List[Dict[str, Any]]) -> str:
    """Fingerprint immutable markup/segment order, including table spans and targets."""
    relevant = []
    for token in tokens:
        if token["kind"] == "segment":
            relevant.append(("segment", token["id"]))
            continue
        raw = token.get("value", "")
        match = re.match(r"</?([A-Za-z0-9:-]+)", raw)
        if not match:
            continue
        tag = match.group(1).lower()
        attrs = []
        for name in ("id", "href", "data-cell-id", "data-block-id", "data-page", "rowspan", "colspan"):
            found = re.search(rf'\s{name}=["\']([^"\']*)["\']', raw, flags=re.I)
            if found:
                attrs.append((name, found.group(1)))
        relevant.append(("end" if raw.startswith("</") else "start", tag, attrs))
    return digest({"markup": relevant, "segment_ids": [segment["id"] for segment in segments]})


def translation_revision(model: Dict[str, Any]) -> str:
    payload = {
        "validator_version": VALIDATOR_VERSION,
        "config": model["config"], "source_revision": model["source_revision"],
        "glossary_revision": model["glossary_revision"],
        "assembler_version": model.get("assembler_version"),
        "assembly": [{key: unit.get(key) for key in ("id", "assembler_version", "enabled", "source_segment_ids", "assembled_text", "spans")}
                     for unit in model.get("translation_units", [])],
        "segments": [{key: segment.get(key) for key in ("id", "baseline_text", "translated_text", "final_text", "status", "warnings", "manual_edited", "term_states", "provenance")}
                     for segment in model["segments"]],
        "segment_assembly": [{key: segment.get(key) for key in ("id", "translation_unit_id", "translation_unit_member_index", "translation_unit_enabled", "translation_unit_source_span")}
                             for segment in model["segments"]],
    }
    return digest(payload)


def create_model(files_dir: str, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    clean = validate_config(config)
    variant, source_path, source_revision = resolve_source(files_dir, job_id, clean["source_variant"])
    with open(source_path, encoding="utf-8") as handle: source_content = handle.read()
    source_format = "text" if source_path.lower().endswith(".txt") else "html"
    source_html = text_source_to_html(source_content) if source_format == "text" else source_content
    tokens, segments = extract_document(source_html)
    translation_units = assemble_translation_units(segments)
    glossary = load_glossary(files_dir, job_id)
    previous = read_json(os.path.join(translation_dir(files_dir, job_id), "translation.json"))
    manual = {s["id"]: s for s in previous.get("segments", []) if s.get("manual_edited")}
    if clean["preserve_manual_final"]:
        for segment in segments:
            saved = manual.get(segment["id"])
            if saved and saved.get("source_text") == segment["source_text"]:
                segment.update(final_text=saved.get("final_text"), manual_edited=True, status="manual-final")
                if clean["manual_strategy"] == "rebase":
                    segment["warnings"] = ["manual_final_needs_rebase_review"]
    now = utc_now()
    detected, confidence, language_warning = detect_language(segments)
    model = {
        "schema_version": SCHEMA_VERSION, "job_id": job_id, "source_variant": variant,
        "source_format": source_format,
        "source_revision": source_revision, "glossary_revision": glossary["revision"],
        "translation_revision": None, "config": clean, "detected_language": detected,
        "language_confidence": confidence, "assembler_version": ASSEMBLER_VERSION,
        "segments": segments, "translation_units": translation_units, "tokens": tokens,
        "structure_signature": structure_signature(tokens, segments),
        "status": "queued", "warnings": [language_warning] if language_warning else [], "created_at": previous.get("created_at") or now,
        "updated_at": now, "completed_at": None,
    }
    model["translation_revision"] = translation_revision(model)
    return model


def save_model(files_dir: str, job_id: str, model: Dict[str, Any]) -> Dict[str, Any]:
    model["updated_at"] = utc_now()
    model["translation_revision"] = translation_revision(model)
    atomic_write_json(os.path.join(translation_dir(files_dir, job_id), "translation.json"), model)
    return model


def export_results(files_dir: str, job_id: str, model: Dict[str, Any]) -> Dict[str, str]:
    if structure_signature(model["tokens"], model["segments"]) != model.get("structure_signature"):
        raise ValueError("Translation structure changed")
    directory = translation_dir(files_dir, job_id)
    os.makedirs(directory, exist_ok=True)
    html_content = render_html(model["tokens"], model["segments"], title=f"Translated {job_id}")
    text_content = "\n\n".join(
        segment_output_text(s)
        for s in model["segments"]
        if not suppress_continuation(s)
    )
    html_path, text_path = os.path.join(directory, "translated.html"), os.path.join(directory, "translated.txt")
    atomic_write_text(html_path, html_content)
    atomic_write_text(text_path, text_content + ("\n" if text_content else ""))
    # Mirror translated HTML into the normal export directory so EPUB can use the existing guarded pipeline.
    atomic_write_text(os.path.join(safe_job_dir(files_dir, job_id), "export", "translated.html"), html_content)
    return {"html": html_path, "text": text_path}
