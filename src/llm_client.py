"""
Local LLM Client Wrapper (OpenAI-compatible) for Phase 3 text correction.
Supports http://127.0.0.1:1234 (e.g. LM Studio / vLLM / llama.cpp)
"""
from typing import Dict, Any, List, Optional
import logging
import json
import os
import re
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

from src import config
from src.cli_process import run_cli_process, CliCancelledError, CliOutputError

logger = logging.getLogger(__name__)

ALLOWED_CLI_ENV_VARS = {
    "PATH", "PATHEXT", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    "PYTHONPATH", "LANG", "LC_ALL",
}
MAX_CLI_OUTPUT_BYTES = 5 * 1024 * 1024


def get_safe_cli_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.upper() in ALLOWED_CLI_ENV_VARS}


class LocalLLMClient:
    """
    Client for interacting with local OpenAI-compatible LLM servers.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        transport: Optional[str] = None,
        cli_provider: Optional[str] = None,
    ):
        settings = config.get_llm_config()
        self.transport = (transport or settings.get("transport") or "api").strip().lower()
        if self.transport not in {"api", "cli"}:
            raise ValueError("Local AI transport must be api or cli")
        self.cli_provider = (cli_provider or settings.get("cli_provider") or "codex").strip().lower()
        if self.cli_provider not in {"codex", "gemini", "agy", "claude", "lms"}:
            raise ValueError("Local AI CLI provider must be codex, gemini, agy, claude or lms")
        self.base_url = (base_url or settings["base_url"]).rstrip("/")
        self.model = model or settings["model"]
        if self.transport == "cli":
            self._validate_cli_model()
        self.api_key = config.LLM_API_KEY if api_key is None else api_key
        self.timeout = settings["timeout"] if timeout is None else timeout
        self.cli_path = self._resolve_cli() if self.transport == "cli" else None
        retry_options = {} if max_retries is None else {"max_retries": max_retries}
        self._client = None if self.transport == "cli" else OpenAI(
            base_url=self.base_url, api_key=self.api_key, timeout=self.timeout, **retry_options)
        self._html_reasoning_checked = False
        self._html_native_url = None

    @staticmethod
    def _model_name_is_safe(model: str) -> bool:
        return bool(isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_:.@+-]{0,199}", model))

    def _validate_cli_model(self):
        # Batch-file CLI shims must never receive shell metacharacters in model argv.
        if not self._model_name_is_safe(self.model):
            raise ValueError("AI CLI model must be a non-empty model identifier without shell metacharacters")

    @staticmethod
    def _resolve_lms_cli() -> Optional[str]:
        configured = os.getenv("LMS_CLI_PATH", "").strip()
        candidates = [configured, shutil.which("lms"), str(Path.home()/".lmstudio"/"bin"/"lms.exe")]
        for candidate in candidates:
            if not candidate: continue
            path = Path(candidate).expanduser()
            if path.is_file() and path.name.lower() in {"lms", "lms.exe", "lms.cmd"}:
                return str(path.resolve())
        return None

    def _resolve_cli(self) -> Optional[str]:
        if self.cli_provider == "lms":
            return self._resolve_lms_cli()
        allowed_names = {
            "codex": {"codex", "codex.exe", "codex.cmd"},
            "gemini": {"gemini", "gemini.exe", "gemini.cmd", "gemini.ps1"},
            "agy": {"agy", "agy.exe", "agy.cmd"},
            "claude": {"claude", "claude.exe", "claude.cmd", "claude.ps1"},
        }
        candidate = shutil.which(self.cli_provider)
        if not candidate:
            return None
        path = Path(candidate).expanduser()
        return str(path.resolve()) if path.is_file() and path.name.lower() in allowed_names[self.cli_provider] else None

    @staticmethod
    def _clean_cli_output(value: str) -> str:
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value or "").strip()

    def _run_lms(self, args: List[str], timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        if not self.cli_path:
            raise RuntimeError("LM Studio CLI (lms) not found")
        return self._run_cli(args, timeout=timeout)

    def _run_cli(self, args: List[str], *, input_text: Optional[str] = None,
                 timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        if not self.cli_path:
            raise RuntimeError(f"AI CLI '{self.cli_provider}' not found")
        workspace = config.ROOT_DIR / "data" / "ai_cli_workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            completed = run_cli_process([self.cli_path, *args], input_text=input_text,
                timeout=timeout or self.timeout, cwd=str(workspace), env=get_safe_cli_env(),
                cancel_event=getattr(self, "cancel_event", None), max_output_bytes=MAX_CLI_OUTPUT_BYTES)
        except subprocess.TimeoutExpired:
            logger.warning(f"AI CLI '{self.cli_provider}' timed out after {timeout or self.timeout}s")
            raise
        return completed

    @staticmethod
    def _extract_cli_json_output(value: str) -> str:
        cleaned = LocalLLMClient._clean_cli_output(value)

        def unwrap(candidate: Any) -> Optional[str]:
            """Find the model payload inside provider-specific JSON envelopes.

            Gemini and AGY print modes may wrap the final text in nested result,
            message or content objects.  Prefer a complete translation payload so
            the strict provider validator still owns schema and ID validation.
            """
            if isinstance(candidate, str):
                text = candidate.strip()
                if re.match(r"<(?:thought|thinking|analysis)\b|```", text, flags=re.I):
                    raise CliOutputError("AI CLI returned reasoning or Markdown outside JSON")
                try:
                    nested = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text or None
                return unwrap(nested) or text
            if isinstance(candidate, dict):
                if isinstance(candidate.get("segments"), list):
                    return json.dumps(candidate, ensure_ascii=False)
                for key in ("response", "result", "content", "text", "output", "message", "data", "parts"):
                    resolved = unwrap(candidate.get(key))
                    if resolved:
                        return resolved
            if isinstance(candidate, list):
                for item in candidate:
                    resolved = unwrap(item)
                    if resolved:
                        return resolved
            return None

        try:
            payload = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            return cleaned
        return unwrap(payload) or cleaned

    @staticmethod
    def _extract_agy_stream_response(value: str) -> str:
        """Return the terminal response from AGY's documented NDJSON protocol."""
        result = None
        for line in LocalLLMClient._clean_cli_output(value).splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "result" and isinstance(event.get("result"), dict):
                result = event["result"]
        if not result:
            raise RuntimeError("AGY CLI returned no terminal stream result")
        if str(result.get("status", "")).upper() != "SUCCESS":
            raise RuntimeError(str(result.get("error") or "AGY CLI generation failed"))
        response = result.get("response")
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("AGY CLI returned an empty response")
        return response

    def _cli_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        self._validate_cli_model()
        combined = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        if self.cli_provider == "lms":
            if len(combined) > 24_000:
                raise RuntimeError("CLI prompt exceeds 24,000 characters; use Local API or a smaller batch")
            completed = self._run_lms(["chat", self.model, "-p", combined, "--ttl", "1",
                                       "--reasoning", "off", "--dont-fetch-catalog", "-y"])
            content = self._clean_cli_output(completed.stdout)
        elif self.cli_provider == "codex":
            workspace = config.ROOT_DIR / "data" / "ai_cli_workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            schema_file = config.ROOT_DIR / "data" / "ai_cli_schemas" / "translation_response_schema.json"
            codex_args = [
                "exec", "-", "--ephemeral", "--sandbox", "read-only", "--ignore-user-config",
                "--ignore-rules", "--skip-git-repo-check", "--color", "never", "-C", str(workspace),
                "--model", self.model,
            ]
            if schema_file.is_file():
                codex_args.extend(["--output-schema", str(schema_file.resolve())])
            completed = self._run_cli(codex_args, input_text=combined)
            content = self._clean_cli_output(completed.stdout)
        elif self.cli_provider == "gemini":
            completed = self._run_cli([
                "-p", "ตอบตามข้อมูลจาก stdin เท่านั้น ห้ามใช้เครื่องมือ และคืนผลลัพธ์เท่านั้น",
                "--output-format", "json", "--approval-mode", "plan", "--sandbox",
                "--model", self.model,
            ], input_text=combined)
            content = self._extract_cli_json_output(completed.stdout)
        elif self.cli_provider == "agy":
            # AGY print mode accepts documents safely through the documented
            # stream-json stdin protocol.  Never put document text in argv.
            stream_request = json.dumps({"event": "user", "message": {"content": combined}}, ensure_ascii=False) + "\n"
            completed = self._run_cli([
                "--input-format", "stream-json", "--output-format", "stream-json",
                "--mode", "plan", "--sandbox", "--disable-slash-commands",
                "--print-timeout", f"{max(1, int(self.timeout))}s",
                "--model", self.model,
            ], input_text=stream_request)
            content = self._extract_cli_json_output(self._extract_agy_stream_response(completed.stdout))
        else:
            completed = self._run_cli([
                "-p", "ตอบตามข้อมูลจาก stdin เท่านั้น คืนผลลัพธ์เท่านั้น และห้ามใช้เครื่องมือ",
                "--input-format", "text", "--output-format", "json",
                "--permission-mode", "plan", "--max-turns", "1",
                "--model", self.model,
                "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch",
            ], input_text=combined)
            content = self._extract_cli_json_output(completed.stdout)
        if completed.returncode != 0 or not content:
            detail = self._clean_cli_output(completed.stderr) or f"{self.cli_provider} CLI returned no output"
            raise RuntimeError(detail)
        return content

    def generate_html_annotations(self, prompt: str, temperature: float = 0.0,
                                  max_tokens: int = 1600) -> str:
        """Disable thinking per HTML request only when LM Studio advertises support."""
        if self.transport == "cli":
            return self._cli_generate(prompt)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        root_url = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        if not self._html_reasoning_checked:
            self._html_reasoning_checked = True
            try:
                request = urllib.request.Request(f"{root_url}/api/v1/models", headers=headers)
                with urllib.request.urlopen(request, timeout=min(self.timeout, 5.0)) as response:
                    for model in json.load(response).get("models", []):
                        identifiers = [model.get("key")] + [
                            instance.get("id") for instance in model.get("loaded_instances", [])]
                        reasoning = model.get("capabilities", {}).get("reasoning", {})
                        if self.model in identifiers and "off" in reasoning.get("allowed_options", []):
                            self._html_native_url = f"{root_url}/api/v1/chat"
                            break
            except (urllib.error.URLError, TimeoutError, ValueError, TypeError, AttributeError):
                # Other OpenAI-compatible servers need no LM Studio support.
                pass
        if not self._html_native_url:
            return self.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
        try:
            body = {"model": self.model, "input": prompt, "temperature": temperature,
                    "max_output_tokens": max_tokens, "reasoning": "off", "store": False}
            request = urllib.request.Request(self._html_native_url,
                data=json.dumps(body).encode("utf-8"),
                headers={**headers, "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
            content = "\n".join(item.get("content", "") for item in payload.get("output", [])
                                if item.get("type") == "message")
            if not content.strip():
                raise RuntimeError("Local AI returned no HTML annotations")
            return content
        except TimeoutError as exc:
            raise RuntimeError(f"Timeout after {self.timeout}s") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local AI HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Local AI connection error: {exc.reason}") from exc

    def check_health(self) -> Dict[str, Any]:
        """
        Check connectivity to the local server and verify model availability.
        Returns a dict with 'status', 'available_models', 'model_found', and error details if any.
        """
        if self.transport == "cli":
            if not self.cli_path:
                return {"status":"connection_error","transport":"cli","configured_model":self.model,
                        "cli_provider":self.cli_provider,"model_found":False,"available_models":[],
                        "error":f"AI CLI '{self.cli_provider}' not found"}
            try:
                if self.cli_provider == "lms":
                    completed=self._run_lms(["ls","--llm","--json",self.model],timeout=min(self.timeout,15))
                    output=self._clean_cli_output(completed.stdout)
                    inventory = json.loads(output)
                    def model_keys(value):
                        if isinstance(value, dict):
                            for key, item in value.items():
                                if key in {"key", "modelKey", "model_key"} and isinstance(item, str):
                                    yield item
                                elif isinstance(item, (dict, list)):
                                    yield from model_keys(item)
                        elif isinstance(value, list):
                            for item in value:
                                yield from model_keys(item)
                    available_models = list(model_keys(inventory))
                    found=completed.returncode==0 and self.model in available_models
                    error = None if found else (self._clean_cli_output(completed.stderr) or f"Model '{self.model}' not found by LM Studio CLI")
                else:
                    completed=self._run_cli(["--version"],timeout=min(self.timeout,10))
                    output=self._clean_cli_output(completed.stdout or completed.stderr)
                    installed=completed.returncode == 0 and bool(output)
                    # A version string proves installation, not authentication or model access.
                    return {"status":"unverified" if installed else "error", "transport":"cli",
                            "cli_provider":self.cli_provider,"configured_model":self.model,
                            "installed":installed,"model_found":False,"authentication":"not_verified",
                            "available_models":[],"cli_version":output if installed else None,
                            "error":f"AI CLI '{self.cli_provider}' authentication/model access could not be verified; generation blocked"}
                return {"status":"connected" if found else "model_not_found","transport":"cli",
                        "cli_provider":self.cli_provider,"configured_model":self.model,"model_found":found,
                        "available_models":available_models,"authentication":"not_required",
                        "error":error}
            except subprocess.TimeoutExpired:
                return {"status":"timeout","transport":"cli","configured_model":self.model,
                        "model_found":False,"available_models":[],"error":"LM Studio CLI health check timed out"}
            except Exception as exc:
                return {"status":"error","transport":"cli","configured_model":self.model,
                        "model_found":False,"available_models":[],"error":str(exc)}
        try:
            models_response = self._client.models.list()
            available_model_ids = [m.id for m in models_response.data]
            model_found = self.model in available_model_ids

            return {
                "status": "connected" if model_found else "model_not_found",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_found": model_found,
                "available_models": available_model_ids,
                "error": None if model_found else f"Model '{self.model}' not found on server.",
            }
        except APIConnectionError as e:
            return {
                "status": "connection_error",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_found": False,
                "available_models": [],
                "error": f"Cannot connect to local LLM server at {self.base_url}: {str(e)}",
            }
        except Exception as e:
            return {
                "status": "error",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_found": False,
                "available_models": [],
                "error": str(e),
            }

    def preflight(self) -> Dict[str, Any]:
        """Perform strict preflight validation before starting any generation."""
        health = self.check_health()
        if health.get("status") not in {"connected", "healthy"} or health.get("model_found") is not True:
            error = health.get("error") or f"Preflight check failed for {self.transport} ({self.cli_provider if self.transport == 'cli' else self.base_url})"
            raise RuntimeError(error)
        return health

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute chat completion with fallback on failure.
        Returns a dictionary containing 'success', 'content', 'status', 'error'.
        """
        if self.transport == "cli":
            try:
                prompt=(messages[0].get("content", "") if len(messages)==1 and messages[0].get("role")=="user" else
                        "\n\n".join(f"{item.get('role','user').upper()}: {item.get('content','')}" for item in messages))
                return {"success":True,"status":"completed","finish_reason":"stop",
                        "content":self._cli_generate(prompt),"error":None,"raw_response":None}
            except subprocess.TimeoutExpired:
                return {"success":False,"status":"timeout","content":"","error":f"Timeout after {self.timeout}s"}
            except CliCancelledError as exc:
                return {"success":False,"status":"cancelled","content":"","error":str(exc)}
            except CliOutputError as exc:
                return {"success":False,"status":"invalid_response","content":"","error":str(exc)}
            except Exception as exc:
                return {"success":False,"status":"error","content":"","error":str(exc)}
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if response_format is not None:
                kwargs["response_format"] = response_format

            resp = self._client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            content = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", None)
            is_truncated = finish_reason == "length"
            return {
                "success": not is_truncated,
                "status": "truncated" if is_truncated else "completed",
                "finish_reason": finish_reason,
                "content": content,
                "error": "Generation truncated by max_tokens limit" if is_truncated else None,
                "raw_response": resp,
            }
        except APITimeoutError as e:
            logger.warning(f"LLM request timed out after {self.timeout}s: {e}")
            return {
                "success": False,
                "status": "timeout",
                "content": "",
                "error": f"Timeout after {self.timeout}s",
            }
        except APIConnectionError as e:
            logger.warning(f"LLM server connection error: {e}")
            return {
                "success": False,
                "status": "connection_error",
                "content": "",
                "error": f"Connection error: {str(e)}",
            }
        except APIError as e:
            logger.warning(f"LLM API error: {e}")
            return {
                "success": False,
                "status": "api_error",
                "content": "",
                "error": f"API error: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Unexpected error calling LLM: {e}")
            return {
                "success": False,
                "status": "error",
                "content": "",
                "error": str(e),
            }

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Convenience wrapper around chat_completion for single-prompt text generation.
        Returns the generated response content, or raises RuntimeError on failure.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        res = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not res.get("success"):
            err_msg = res.get("error") or f"LLM generation failed ({res.get('status')})"
            error = RuntimeError(err_msg)
            error.code = res.get("status", "error")
            raise error
        return res.get("content", "")
