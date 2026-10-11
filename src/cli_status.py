"""Read-only discovery for supported AI CLI adapters."""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import os
import re
import shutil
import subprocess
import json
from typing import Any

from src.config import ROOT_DIR
from src.file_utils import atomic_write_json


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
STATUS_PATH = ROOT_DIR / "data" / "ai_cli_status.json"
_ADAPTERS = [
    ("codex", "Codex CLI", "codex", True),
    ("gemini", "Gemini CLI", "gemini", True),
    ("agy", "AGY CLI", "agy", True),
    ("claude", "Claude CLI", "claude", True),
    ("lms", "LM Studio CLI", "lms", False),
]


def _clean(value: str, limit: int = 1200) -> str:
    text = _ANSI_RE.sub("", value or "").replace("\r", "").strip()
    return text[:limit]


def _run(path: str, args: list[str], timeout: float = 6.0) -> dict[str, Any]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=flags,
        )
        return {
            "returncode": result.returncode,
            "stdout": _clean(result.stdout),
            "stderr": _clean(result.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "", "timed_out": True}
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": _clean(str(exc)), "timed_out": False}


def _version(path: str, args: list[str], timeout: float = 15.0) -> tuple[str | None, str | None]:
    result = _run(path, args, timeout=timeout)
    if result["timed_out"]:
        return None, "ตรวจ version เกินเวลาที่กำหนด"
    output = result["stdout"] or result["stderr"]
    lines = [line.strip() for line in output.splitlines() if line.strip() and not line.startswith("WARNING:")]
    if result["returncode"] == 0 and lines:
        return lines[-1][:160], None
    return None, (lines[-1][:240] if lines else "ตรวจ version ไม่สำเร็จ")


def _base_status(adapter_id: str, label: str, command: str, primary: bool) -> tuple[dict[str, Any], str | None]:
    path = shutil.which(command)
    item: dict[str, Any] = {
        "id": adapter_id,
        "label": label,
        "primary": primary,
        "installed": bool(path),
        "command": command,
        "version": None,
        "status": "not_installed" if not path else "checking",
        "authentication": "not_checked",
        "local_runtime": "not_checked",
        "detail": "ไม่พบคำสั่งใน PATH" if not path else None,
    }
    return item, path


def _codex_status() -> dict[str, Any]:
    item, path = _base_status("codex", "Codex CLI", "codex", True)
    if not path:
        return item
    version, error = _version(path, ["--version"])
    item["version"] = version
    if error:
        item.update(status="error", detail=error)
        return item
    login = _run(path, ["login", "status"])
    login_text = "\n".join(filter(None, [login["stdout"], login["stderr"]]))
    logged_in = login["returncode"] == 0 and "logged in" in login_text.lower()
    item.update(
        status="ready" if logged_in else "needs_auth",
        authentication="ready" if logged_in else "required",
        local_runtime="supported",
        detail="พร้อมใช้งาน" if logged_in else (_clean(login_text, 300) or "ยังไม่ได้เข้าสู่ระบบ"),
    )
    return item


def _gemini_status() -> dict[str, Any]:
    item, path = _base_status("gemini", "Gemini CLI", "gemini", True)
    if not path:
        return item
    version, error = _version(path, ["--version"], timeout=30.0)
    item["version"] = version
    if error:
        item.update(status="error", detail=error)
        return item
    local = _run(path, ["gemma", "status"])
    local_text = "\n".join(filter(None, [local["stdout"], local["stderr"]]))
    local_ready = local["returncode"] == 0
    item.update(
        status="ready",
        authentication="check_on_use",
        local_runtime="ready" if local_ready else "not_ready",
        detail=("ติดตั้งแล้ว; cloud auth ตรวจเมื่อเรียกใช้งาน" +
                ("; Gemma local พร้อม" if local_ready else "; Gemma local ยังไม่พร้อม")),
        local_detail=None if local_ready else _clean(local_text, 600),
    )
    return item


def _lms_status() -> dict[str, Any]:
    item, path = _base_status("lms", "LM Studio CLI", "lms", False)
    if not path:
        return item
    version, error = _version(path, ["--version"])
    item["version"] = version
    item.update(
        status="ready" if version else "error",
        authentication="not_required",
        local_runtime="ready" if version else "not_checked",
        detail="ติดตั้งแล้ว (adapter รอง)" if version else error,
    )
    return item


def _agy_status() -> dict[str, Any]:
    item, path = _base_status("agy", "AGY CLI", "agy", True)
    if not path:
        return item
    version, error = _version(path, ["--version"])
    item["version"] = version
    item.update(
        status="ready" if version else "error",
        authentication="check_on_use",
        local_runtime="not_supported",
        detail="ติดตั้งแล้ว; ใช้เป็น Gemini command interface และตรวจ cloud auth เมื่อเรียกใช้งาน" if version else error,
    )
    return item


def _claude_status() -> dict[str, Any]:
    item, path = _base_status("claude", "Claude CLI", "claude", True)
    if not path:
        return item
    version, error = _version(path, ["--version"])
    item["version"] = version
    item.update(
        status="ready" if version else "error",
        authentication="check_on_use",
        local_runtime="not_supported",
        detail="ติดตั้งแล้ว; ตรวจ Anthropic authentication เมื่อเรียกใช้งาน" if version else error,
    )
    return item


def get_ai_cli_status() -> dict[str, Any]:
    """Return local executable/readiness status without sending document data."""
    checks = [_codex_status, _gemini_status, _agy_status, _claude_status, _lms_status]
    with ThreadPoolExecutor(max_workers=len(checks), thread_name_prefix="ai-cli-status") as executor:
        adapters = list(executor.map(lambda check: check(), checks))
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "adapters": adapters,
    }


def empty_ai_cli_status() -> dict[str, Any]:
    return {"checked_at": None, "adapters": [{
        "id": adapter_id, "label": label, "primary": primary, "installed": None,
        "command": command, "version": None, "status": "not_checked",
        "authentication": "not_checked", "local_runtime": "not_checked",
        "detail": "กดตรวจสอบสถานะเพื่ออ่านข้อมูลจากเครื่อง",
    } for adapter_id, label, command, primary in _ADAPTERS]}


def load_ai_cli_status() -> dict[str, Any]:
    try:
        with STATUS_PATH.open(encoding="utf-8") as handle:
            data=json.load(handle)
        if isinstance(data,dict) and isinstance(data.get("adapters"),list):
            return data
    except (FileNotFoundError, OSError, ValueError, TypeError):
        pass
    return empty_ai_cli_status()


def check_and_store_ai_cli_status() -> dict[str, Any]:
    data=get_ai_cli_status()
    atomic_write_json(str(STATUS_PATH),data)
    return data
