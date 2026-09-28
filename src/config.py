"""
Centralized Configuration Module for OCR & AI Pipeline.
Loads settings from environment variables or .env file with safe defaults.
"""
from pathlib import Path
import os
import re
from dotenv import load_dotenv

# Base project directory
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Load environment variables from .env if present
load_dotenv(ENV_PATH)

# ------------------------------------------------------------------------------
# Local LLM Configuration (Phase 3: AI Text Correction)
# ------------------------------------------------------------------------------
# Local LLM Endpoint (e.g., LM Studio, Ollama, vLLM, llama.cpp server)
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")

# Target Model identifier
LLM_MODEL: str = os.getenv("LLM_MODEL", "google/gemma-3-1b")

# API key for OpenAI compatibility (usually dummy string for local servers)
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "not-needed")

# Default request timeout in seconds
LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60.0"))

# ------------------------------------------------------------------------------
# Server & Network Configuration (Phase 6: Deployment & Loopback Binding)
# ------------------------------------------------------------------------------
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
LOCALHOST_ONLY: bool = os.getenv("LOCALHOST_ONLY", "true").lower() in ("true", "1", "yes")

# ------------------------------------------------------------------------------
# Data Retention & Cleanup Configuration (Phase 6)
# ------------------------------------------------------------------------------
RETENTION_SECONDS: float = float(os.getenv("RETENTION_SECONDS", "86400.0"))  # Default 24 hours


def get_llm_config() -> dict:
    """Returns local LLM settings without exposing its API key."""
    return {
        "base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "timeout": LLM_TIMEOUT,
        "api_key_configured": bool(LLM_API_KEY and LLM_API_KEY != "not-needed"),
    }


def update_llm_config(
    *,
    base_url: str,
    model: str,
    timeout: float,
    api_key: str | None = None,
) -> dict:
    """Persists local LLM settings and updates this running process immediately."""
    global LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT, LLM_API_KEY

    updates = {
        "LLM_BASE_URL": base_url.rstrip("/"),
        "LLM_MODEL": model,
        "LLM_TIMEOUT": str(timeout),
    }
    if api_key is not None:
        updates["LLM_API_KEY"] = api_key

    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    output_lines = []
    for line in existing_lines:
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(2) in remaining:
            output_lines.append(f"{match.group(1)}{match.group(2)}={remaining.pop(match.group(2))}")
        else:
            output_lines.append(line)
    output_lines.extend(f"{key}={value}" for key, value in remaining.items())

    temp_path = ENV_PATH.with_suffix(".tmp")
    temp_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    temp_path.replace(ENV_PATH)

    LLM_BASE_URL = updates["LLM_BASE_URL"]
    LLM_MODEL = updates["LLM_MODEL"]
    LLM_TIMEOUT = float(timeout)
    if api_key is not None:
        LLM_API_KEY = api_key
    return get_llm_config()
