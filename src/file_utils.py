import os
import json
import tempfile
from typing import Any


def atomic_write_text(filepath: str, content: str, encoding: str = "utf-8") -> None:
    """
    Writes text atomically using temp file in the same directory,
    ensuring flush + os.fsync and os.replace.
    """
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_")
    try:
        with os.fdopen(temp_fd, "w", encoding=encoding, newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise


def atomic_write_json(filepath: str, data: Any, indent: int = 2) -> None:
    """
    Writes JSON data atomically using temp file in the same directory,
    ensuring flush + os.fsync and os.replace.
    """
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise


def atomic_write_bytes(filepath: str, content: bytes) -> None:
    """Writes binary content atomically in the destination directory."""
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_")
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise
