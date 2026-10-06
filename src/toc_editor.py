"""Phase 9 editable TOC model built on the Phase 8 EPUB pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from src.file_utils import atomic_write_json


TOC_SCHEMA_VERSION = "9.0"
MAX_TOC_ENTRIES = 5000
MAX_TOC_BYTES = 2 * 1024 * 1024
ENTRY_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def _canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def toc_revision(entries: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical(entries).encode("utf-8")).hexdigest()[:24]


def _entry_id(target_id: str, index: int) -> str:
    digest = hashlib.sha256(f"{target_id}\0{index}".encode("utf-8")).hexdigest()[:12]
    return f"toc-{digest}"


def build_targets(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    seen = set()
    for chapter in chapters:
        start_id = f"chapter-start-{chapter['index']:03d}"
        targets.append({
            "target_id": start_id,
            "type": "chapter_start",
            "label": chapter["title"],
            "context": f"ต้นบท {chapter['index']}: {chapter['title']}",
            "level": 1,
            "chapter_filename": chapter["filename"],
            "fragment_id": "",
            "preview_fragment": f"chapter-{chapter['index']:03d}",
            "match_key": f"chapter:{chapter['index']}:{chapter['title'].strip().casefold()}",
        })
        for block in chapter["blocks"]:
            if block.get("tag") not in {"h1", "h2", "h3"} or not block.get("id"):
                continue
            target_id = str(block["id"])
            if target_id in seen:
                raise ValueError(f"Duplicate stable target id: {target_id}")
            seen.add(target_id)
            label = str(block.get("visible_text", "")).strip()
            level = int(block["tag"][1])
            page = str(block.get("page") or "")
            targets.append({
                "target_id": target_id,
                "type": "heading",
                "label": label,
                "context": f"{block['tag']} · {('หน้า ' + page + ' · ') if page else ''}{label}",
                "level": level,
                "chapter_filename": chapter["filename"],
                "fragment_id": target_id,
                "preview_fragment": target_id,
                "match_key": f"heading:{block['tag']}:{label.casefold()}",
            })
    return targets


def automatic_entries(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    headings = [target for target in targets if target["type"] == "heading"]
    selected = headings or [target for target in targets if target["type"] == "chapter_start"]
    entries: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []
    for index, target in enumerate(selected):
        raw_level = int(target.get("level", 1)) if target["type"] == "heading" else 1
        level = max(1, min(3, raw_level))
        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()
        if level > 1 and not stack:
            level = 1
        parent_id = stack[-1]["entry_id"] if stack and level > 1 else None
        entry = {
            "entry_id": _entry_id(target["target_id"], index),
            "label": target["label"][:300],
            "parent_id": parent_id,
            "level": level,
            "order": index,
            "target_id": target["target_id"],
            "target_match_key": target["match_key"],
            "status": "auto-generated",
        }
        entries.append(entry)
        stack.append(entry)
    return entries


def validate_entries(entries: Any, targets: List[Dict[str, Any]], allow_unresolved: bool = False) -> List[Dict[str, Any]]:
    if not isinstance(entries, list) or not entries:
        raise ValueError("TOC must contain at least one entry")
    if len(entries) > MAX_TOC_ENTRIES:
        raise ValueError(f"TOC exceeds {MAX_TOC_ENTRIES} entries")
    if len(_canonical(entries).encode("utf-8")) > MAX_TOC_BYTES:
        raise ValueError("TOC exceeds 2 MB limit")
    target_ids = {target["target_id"] for target in targets}
    clean: List[Dict[str, Any]] = []
    entry_ids = set()
    used_targets = set()
    for order, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"TOC entry {order + 1} must be an object")
        entry_id = str(raw.get("entry_id", "")).strip()
        if not ENTRY_ID_RE.fullmatch(entry_id) or entry_id in entry_ids:
            raise ValueError(f"Invalid or duplicate TOC entry id: {entry_id or '(empty)'}")
        label = re.sub(r"[\x00-\x1f]", "", str(raw.get("label", ""))).strip()
        if not label:
            raise ValueError(f"TOC entry {entry_id} has an empty label")
        if len(label) > 300:
            raise ValueError(f"TOC entry {entry_id} label exceeds 300 characters")
        try:
            level = int(raw.get("level", 1))
        except (TypeError, ValueError):
            raise ValueError(f"TOC entry {entry_id} has an invalid level")
        if level < 1 or level > 3:
            raise ValueError(f"TOC entry {entry_id} level must be 1-3")
        parent_id = str(raw.get("parent_id") or "") or None
        if level == 1 and parent_id:
            raise ValueError(f"TOC entry {entry_id} level 1 cannot have a parent")
        if level > 1:
            if not parent_id or parent_id not in entry_ids:
                raise ValueError(f"TOC entry {entry_id} has an orphan parent")
            parent = next(item for item in clean if item["entry_id"] == parent_id)
            if int(parent["level"]) != level - 1:
                raise ValueError(f"TOC entry {entry_id} parent level is invalid")
        target_id = str(raw.get("target_id", "")).strip()
        unresolved = target_id not in target_ids
        if unresolved and not allow_unresolved:
            raise ValueError(f"TOC entry {entry_id} has no valid target")
        if not unresolved and target_id in used_targets:
            raise ValueError(f"TOC target is used more than once: {target_id}")
        if not unresolved:
            used_targets.add(target_id)
        entry_ids.add(entry_id)
        clean.append({
            "entry_id": entry_id,
            "label": label,
            "parent_id": parent_id,
            "level": level,
            "order": order,
            "target_id": target_id,
            "target_match_key": str(raw.get("target_match_key", ""))[:500],
            "status": "unresolved" if unresolved else ("user-edited" if raw.get("status") != "auto-generated" else "auto-generated"),
        })
    return clean


def rematch_entries(entries: List[Dict[str, Any]], targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {target["target_id"]: target for target in targets}
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for target in targets:
        by_key.setdefault(target["match_key"], []).append(target)
    matched = 0
    unresolved = []
    output = []
    claimed_targets = {str(entry.get("target_id", "")) for entry in entries
                       if str(entry.get("target_id", "")) in by_id}
    for raw in entries:
        entry = dict(raw)
        target = by_id.get(str(entry.get("target_id", "")))
        resolution = "stable-id"
        if target is None:
            candidates = by_key.get(str(entry.get("target_match_key", "")), [])
            available = [candidate for candidate in candidates if candidate["target_id"] not in claimed_targets]
            if len(available) == 1:
                target = available[0]
                entry["target_id"] = target["target_id"]
                claimed_targets.add(target["target_id"])
                resolution = "unique-rematch"
            else:
                entry["status"] = "unresolved"
                entry["resolution"] = "ambiguous" if candidates else "missing"
                unresolved.append({"entry_id": entry.get("entry_id"), "reason": entry["resolution"]})
        if target is not None:
            entry["target_match_key"] = target["match_key"]
            entry["resolution"] = resolution
            matched += 1
        output.append(entry)
    return {"entries": output, "matched_count": matched, "unresolved": unresolved}


def render_toc_markup(entries: List[Dict[str, Any]], targets: List[Dict[str, Any]], preview: bool = False) -> str:
    clean = validate_entries(entries, targets)
    target_map = {target["target_id"]: target for target in targets}
    nodes: Dict[str, Dict[str, Any]] = {}
    roots: List[Dict[str, Any]] = []
    for entry in clean:
        target = target_map[entry["target_id"]]
        href = ("#" + target["preview_fragment"] if preview else
                "text/" + target["chapter_filename"] + (("#" + target["fragment_id"]) if target["fragment_id"] else ""))
        node = {"label": entry["label"], "href": href, "children": []}
        nodes[entry["entry_id"]] = node
        if entry["parent_id"]:
            nodes[entry["parent_id"]]["children"].append(node)
        else:
            roots.append(node)

    def render(items: List[Dict[str, Any]]) -> str:
        return "<ol>" + "".join(
            '<li><a href="' + html_escape(item["href"], True) + '">' + html_escape(item["label"]) + "</a>" +
            (render(item["children"]) if item["children"] else "") + "</li>" for item in items
        ) + "</ol>"
    return render(roots)


def html_escape(value: Any, quote: bool = False) -> str:
    import html
    return html.escape(str(value), quote=quote)


def load_toc(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def write_toc(path: str, source_revision: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    revision = toc_revision(entries)
    model = {
        "schema_version": TOC_SCHEMA_VERSION,
        "source_revision": source_revision,
        "toc_revision": revision,
        "entries": entries,
    }
    atomic_write_json(path, model)
    return model


def editor_state(job_id: str, files_dir: str = "files", source_variant: str = "auto",
                 chapter_split: str = "heading") -> Dict[str, Any]:
    from src.epub_exporter import _parse_blocks, _read_json, _resolve_source, _safe_job_dir, _split_chapters
    job_dir = _safe_job_dir(files_dir, job_id)
    resolved, source_path, source_revision = _resolve_source(job_dir, source_variant)
    with open(source_path, "r", encoding="utf-8") as stream:
        blocks = _parse_blocks(stream.read())
    meta = _read_json(os.path.join(job_dir, "export", "epub", "epub_meta.json"))
    title = str((meta.get("metadata") or {}).get("title") or f"OCR Document {job_id}")
    chapters = _split_chapters(blocks, chapter_split, title)
    targets = build_targets(chapters)
    path = os.path.join(job_dir, "export", "epub", "toc.json")
    saved = load_toc(path)
    if saved.get("entries"):
        result = rematch_entries(saved["entries"], targets)
        entries = result["entries"]
        unresolved = result["unresolved"]
        matched_count = result["matched_count"]
        revision = saved.get("toc_revision") or toc_revision(saved["entries"])
        generated = False
    else:
        entries = automatic_entries(targets)
        unresolved = []
        matched_count = len(entries)
        revision = toc_revision(entries)
        generated = True
    return {
        "schema_version": TOC_SCHEMA_VERSION,
        "job_id": job_id,
        "source_variant": resolved,
        "source_revision": source_revision,
        "toc_revision": revision,
        "base_preview_revision": meta.get("preview_revision"),
        "chapter_split": chapter_split,
        "generated": generated,
        "source_changed": bool(saved and saved.get("source_revision") != source_revision),
        "entries": entries,
        "targets": targets,
        "unresolved": unresolved,
        "matched_count": matched_count,
    }


def save_editor_toc(job_id: str, entries: List[Dict[str, Any]], base_source_revision: str,
                    base_toc_revision: str, base_preview_revision: Optional[str], files_dir: str = "files",
                    source_variant: str = "auto", chapter_split: str = "heading") -> Dict[str, Any]:
    state = editor_state(job_id, files_dir, source_variant, chapter_split)
    if base_source_revision != state["source_revision"]:
        raise ValueError("Conflict: source revision changed. Re-match the TOC draft.")
    if base_toc_revision != state["toc_revision"]:
        raise ValueError("Conflict: TOC revision changed in another tab.")
    if base_preview_revision != state["base_preview_revision"]:
        raise ValueError("Conflict: EPUB preview/config changed in another tab.")
    clean = validate_entries(entries, state["targets"])
    job_dir = os.path.abspath(os.path.join(files_dir, job_id))
    path = os.path.join(job_dir, "export", "epub", "toc.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    model = write_toc(path, state["source_revision"], clean)
    return {**model, "targets_count": len(state["targets"]), "unresolved": []}


def regenerate_toc(job_id: str, confirm: bool, base_source_revision: str, base_toc_revision: str,
                   base_preview_revision: Optional[str], files_dir: str = "files",
                   source_variant: str = "auto", chapter_split: str = "heading") -> Dict[str, Any]:
    if not confirm:
        raise ValueError("Confirmation required before replacing the edited TOC")
    state = editor_state(job_id, files_dir, source_variant, chapter_split)
    return save_editor_toc(job_id, automatic_entries(state["targets"]), base_source_revision,
                           base_toc_revision, base_preview_revision, files_dir, source_variant, chapter_split)
