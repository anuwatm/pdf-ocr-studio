"""
Local LLM Client Wrapper (OpenAI-compatible) for Phase 3 text correction.
Supports http://127.0.0.1:1234 (e.g. LM Studio / vLLM / llama.cpp)
"""
from typing import Dict, Any, List, Optional
import logging
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
    ):
        settings = config.get_llm_config()
        self.base_url = (base_url or settings["base_url"]).rstrip("/")
        self.model = model or settings["model"]
        self.api_key = config.LLM_API_KEY if api_key is None else api_key
        self.timeout = settings["timeout"] if timeout is None else timeout
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

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
            content = resp.choices[0].message.content or ""
            return {
                "success": True,
                "status": "completed",
                "content": content,
                "error": None,
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
