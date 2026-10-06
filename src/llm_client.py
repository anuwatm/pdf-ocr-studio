"""
Local LLM Client Wrapper (OpenAI-compatible) for Phase 3 text correction.
Supports http://127.0.0.1:1234 (e.g. LM Studio / vLLM / llama.cpp)
"""
from typing import Dict, Any, List, Optional
import logging
import json
import urllib.request
import urllib.error
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

from src import config

logger = logging.getLogger(__name__)


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
    ):
        settings = config.get_llm_config()
        self.base_url = (base_url or settings["base_url"]).rstrip("/")
        self.model = model or settings["model"]
        self.api_key = config.LLM_API_KEY if api_key is None else api_key
        self.timeout = settings["timeout"] if timeout is None else timeout
        retry_options = {} if max_retries is None else {"max_retries": max_retries}
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            **retry_options,
        )
        self._html_reasoning_checked = False
        self._html_native_url = None

    def generate_html_annotations(self, prompt: str, temperature: float = 0.0,
                                  max_tokens: int = 1600) -> str:
        """Disable thinking per HTML request only when LM Studio advertises support."""
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
            raise RuntimeError(err_msg)
        return res.get("content", "")
