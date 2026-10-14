"""Translation provider adapters with a shared result and error contract."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from src.llm_client import LocalLLMClient
from src.translation_core import COMMON_RULE, STYLE_RULES, critical_tokens

LANGUAGES = [
    {"code":"th","name":"ไทย"},{"code":"en","name":"English"},{"code":"zh-CN","name":"简体中文"},
    {"code":"zh-TW","name":"繁體中文"},{"code":"ja","name":"日本語"},{"code":"ko","name":"한국어"},
    {"code":"de","name":"Deutsch"},{"code":"fr","name":"Français"},{"code":"es","name":"Español"},
    {"code":"vi","name":"Tiếng Việt"},{"code":"id","name":"Bahasa Indonesia"},{"code":"ms","name":"Bahasa Melayu"},
]


class TranslationError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error", retryable: bool = False):
        super().__init__(message); self.code = code; self.retryable = retryable


class TranslationProvider(ABC):
    name = "base"
    cloud = False
    def set_cancel_event(self, event):
        self.cancel_event = event
    @abstractmethod
    def capability(self) -> Dict[str, Any]: ...
    @abstractmethod
    def translate(self, segments: List[Dict[str, Any]], config: Dict[str, Any], glossary: List[Dict[str, Any]]) -> List[Dict[str, Any]]: ...
    def preflight(self) -> Dict[str, Any]:
        cap = self.capability()
        if not cap.get("available"):
            raise TranslationError(cap.get("error") or f"Provider '{self.name}' unavailable", "unavailable")
        return cap


def build_cli_protocol_envelope(segments: List[Dict[str, Any]], config: Dict[str, Any],
                                 glossary: List[Dict[str, Any]], request_id: Optional[str] = None) -> Dict[str, Any]:
    """Build canonical UTF-8 JSON envelope for AI CLI protocol."""
    return {
        "schema_version": "10.0",
        "request_id": request_id or f"req-{os.urandom(8).hex()}",
        "task": "translate_document_segments",
        "source_language": config.get("source_language", "auto"),
        "target_language": config.get("target_language", "th"),
        "style": config.get("style", "general"),
        "segments": [{"id": s["id"], "text": s.get("baseline_text") if s.get("baseline_text") is not None else s["source_text"],
                      **({"context_unit": {"id":s["translation_unit_id"],"text":s.get("translation_unit_text", ""),
                                            "member_ids":s.get("translation_unit_member_ids", [])}}
                         if s.get("translation_unit_id") else {})} for s in segments],
        "glossary": glossary,
        "constraints": {
            "no_tools": True,
            "pure_json_output": True,
            "preserve_segment_ids": True,
            "protect_critical_tokens": True,
        }
    }


def _prompt(segments, config, glossary, baseline=False):
    compact = [{"id":s["id"], "text":s.get("baseline_text") if baseline else s["source_text"],
                **({"context_unit": {"id": s["translation_unit_id"],
                                      "text": s.get("translation_unit_text", ""),
                                      "member_ids": s.get("translation_unit_member_ids", []),
                                      "member_index": s.get("translation_unit_member_index")}}
                   if s.get("translation_unit_id") else {})}
               for s in segments]
    language_name=next((row["name"] for row in LANGUAGES if row["code"].lower()==config["target_language"].lower()),config["target_language"])
    style_key = {"ทั่วไป": "general", "นิยาย": "novel", "วิชาการ": "academic", "ราชการ": "official"}.get(config.get("style"), config.get("style", "general"))
    rule = STYLE_RULES.get(style_key, STYLE_RULES.get("general", ""))
    return (f"คุณเป็นนักแปลเอกสาร แปลทุก segment เป็นภาษา {language_name} ({config['target_language']}) รูปแบบ {style_key}\n"
            f"กฎรูปแบบ: {rule}\nกฎร่วม: {COMMON_RULE}\n"
            "ห้ามคัดลอกประโยคภาษาต้นทางทั้งประโยค ยกเว้น code; คงศัพท์เทคนิคได้แต่ข้อความอธิบายต้องเป็นภาษาปลายทาง\n"
            "ข้อความรูปแบบ __PHASE_TOKEN_A__ คือ protected token: ต้องคงอักขระและตำแหน่งเดิมทุกตัว ห้ามแปล แก้ หรือลบ\n"
            "context_unit เป็นบริบทจากบรรทัด OCR ต่อเนื่องและอาจ de-hyphenate แล้ว; ใช้เพื่อเข้าใจประโยค แต่คืน text แยกตาม id เดิมทุกตัว\n"
            "รักษา ID และจำนวนรายการ ห้ามเพิ่ม/ลบ/รวม/สรุป คืน JSON object เท่านั้นรูปแบบ "
            '{"segments":[{"id":"...","text":"..."}]}\n'
            f"Glossary: {json.dumps(glossary, ensure_ascii=False)}\nSegments: {json.dumps(compact, ensure_ascii=False)}")


def _generation_prompt(client, segments, config, glossary, baseline=False):
    prompt = _prompt(segments, config, glossary, baseline=baseline)
    if getattr(client, "transport", None) != "cli":
        return prompt
    envelope = build_cli_protocol_envelope(segments, config, glossary)
    envelope["instructions"] = prompt.split("\nGlossary: ", 1)[0]
    return json.dumps(envelope, ensure_ascii=False)


def _parse_response(content: str, expected: List[str]) -> List[Dict[str, Any]]:
    text = content.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranslationError("Provider returned invalid JSON", "invalid_response") from exc

    def find_rows(obj: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(obj, dict):
            if isinstance(obj.get("segments"), list):
                return obj["segments"]
            for k in ("result", "response", "data", "translation", "output", "items", "parts"):
                nested = find_rows(obj.get(k))
                if nested is not None:
                    return nested
        elif isinstance(obj, list):
            if all(isinstance(item, dict) and "id" in item and ("text" in item or "translation" in item) for item in obj):
                return [{"id": item["id"], "text": item.get("text", item.get("translation", ""))} for item in obj]
            for item in obj:
                nested = find_rows(item)
                if nested is not None:
                    return nested
        return None

    rows = find_rows(payload)
    if not isinstance(rows, list):
        raise TranslationError("Provider response missing segments", "invalid_response")
    ids = [str(row.get("id", "")) for row in rows]
    if ids != expected or len(set(ids)) != len(ids):
        raise TranslationError("Provider changed, reordered or duplicated segment IDs", "invalid_response")
    if any(not isinstance(row.get("text"), str) for row in rows):
        raise TranslationError("Provider returned invalid segment text", "invalid_response")
    return [{"id": row["id"], "text": row["text"]} for row in rows]


def _protect_segments(segments, glossary, baseline=False, protect_critical=True):
    def placeholder_for(index):
        letters=""
        value=index
        while True:
            letters=chr(65+(value%26))+letters
            value=value//26-1
            if value<0:return f"__PHASE_TOKEN_{letters}__"
    protected, maps = [], {}
    for segment in segments:
        text = str(segment.get("baseline_text") if baseline else segment.get("source_text", ""))
        replacements = []
        for entry in glossary:
            expected = entry["source"] if entry.get("do_not_translate") else entry.get("target", "")
            for value in {entry.get("source", ""), expected}:
                if value:
                    replacements.append((value, expected, bool(entry.get("case_sensitive"))))
        if protect_critical:
            for values in critical_tokens(text).values():
                replacements.extend((value, value, True) for value in values)
        mapping = {}
        for value, expected, case_sensitive in sorted(replacements, key=lambda row: len(row[0]), reverse=True):
            pattern = re.compile(re.escape(value), 0 if case_sensitive else re.I)
            while pattern.search(text):
                placeholder = placeholder_for(len(mapping))
                text = pattern.sub(placeholder, text, count=1)
                mapping[placeholder] = expected
        protected.append({**segment, "baseline_text" if baseline else "source_text": text})
        maps[segment["id"]] = mapping
    return protected, maps


def _restore_rows(rows, maps):
    restored = []
    for row in rows:
        text = row["text"]
        for placeholder, value in maps.get(row["id"], {}).items():
            if placeholder in text:
                text = text.replace(placeholder, value)
            else:
                inner = placeholder.strip("_")
                pat = re.compile(r"_+\s*" + re.escape(inner) + r"\s*_+", re.IGNORECASE)
                if pat.search(text):
                    text = pat.sub(value, text)
                else:
                    raise TranslationError("Provider removed a protected token", "invalid_response", True)
        restored.append({**row, "text": text})
    return restored


class LocalTranslationProvider(TranslationProvider):
    name = "local"
    def __init__(self, client=None, *, name="local", label="Local AI ตาม Settings",
                 transport=None, cli_provider=None, cloud=None):
        self.name, self.label = name, label
        self.transport, self.cli_provider = transport, cli_provider
        self.client = client or LocalLLMClient(max_retries=0, timeout=180.0, transport=transport, cli_provider=cli_provider)
        self.cloud = (getattr(self.client,"transport",None)=="cli" and
                      getattr(self.client,"cli_provider",None)!="lms") if cloud is None else cloud
    def capability(self):
        health = self.client.check_health()
        return {"provider":self.name,"label":self.label,"cloud":self.cloud,
                "available":health.get("status") in {"connected","healthy"},
                "transport":getattr(self.client,"transport",self.transport),
                "cli_adapter":getattr(self.client,"cli_provider",self.cli_provider) if getattr(self.client,"transport",self.transport)=="cli" else None,
                "model":getattr(self.client,"model",None),"languages":LANGUAGES,"error":health.get("error")}
    def set_cancel_event(self, event):
        super().set_cancel_event(event)
        self.client.cancel_event = event
    def preflight(self):
        if hasattr(self.client, "preflight"):
            try:
                return self.client.preflight()
            except Exception as exc:
                raise TranslationError(str(exc), "unavailable") from exc
        return super().preflight()
    def translate(self, segments, config, glossary):
        if self.cloud and not config.get("cloud_consent"):
            raise TranslationError("Cloud privacy consent is required", "consent_required")
        # Small local models translate more reliably when numbers/formulas remain visible.
        # The post-translation validator still flags any changed critical token.
        protected,maps=_protect_segments(segments,glossary,protect_critical=False)
        try:
            prompt = _generation_prompt(self.client,protected,config,glossary)
            content = self.client.generate(prompt,temperature=0,max_tokens=4000)
        except TranslationError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", "transient")
            raise TranslationError(str(exc), code, code in {"transient", "timeout", "connection_error"}) from exc
        return _restore_rows(_parse_response(content,[s["id"] for s in segments]),maps)


class GoogleTranslationProvider(TranslationProvider):
    name, cloud = "google", True

    def _settings(self):
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
        credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        api_key = os.getenv("GOOGLE_TRANSLATION_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        if not project and credentials_file and os.path.isfile(credentials_file):
            try:
                with open(credentials_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    project = data.get("project_id", "").strip()
            except Exception:
                pass
        return project, location, credentials_file, api_key

    def capability(self):
        project, location, credentials_file, api_key = self._settings()
        has_auth_lib = False
        try:
            import google.auth  # type: ignore
            has_auth_lib = True
        except ImportError:
            pass

        detected = project
        if not detected and has_auth_lib:
            try:
                import google.auth
                _, detected = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-translation"])
            except Exception:
                pass

        available = bool((has_auth_lib and detected) or api_key)
        error = None
        if not available:
            if not has_auth_lib and not api_key:
                error = "google-auth is not installed"
            elif not detected and not api_key:
                error = "GOOGLE_CLOUD_PROJECT is not configured"

        model = "Google Cloud Translation v3" if detected else ("Google Cloud Translation (API Key)" if api_key else "Google Cloud Translation v3")
        return {"provider": self.name, "cloud": True, "available": available, "languages": LANGUAGES,
                "model": model, "error": error}

    def translate(self, segments, config, glossary):
        import html
        if not config.get("cloud_consent"):
            raise TranslationError("Cloud privacy consent is required", "consent_required")
        project, location, credentials_file, api_key = self._settings()
        protected, maps = _protect_segments(segments, glossary)
        contents = [s["source_text"] for s in protected]
        source_lang = config["source_language"] if config.get("source_language") != "auto" else None
        target_lang = config["target_language"]

        # Option 1: Cloud Translation v3 via ADC / Service Account
        auth_exc = None
        if project:
            try:
                import google.auth  # type: ignore
                from google.auth.transport.requests import Request  # type: ignore
                credentials, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-translation"])
                project = project or detected_project
                credentials.refresh(Request())
                url = f"https://translation.googleapis.com/v3/projects/{project}/locations/{location}:translateText"
                body = {"contents": contents, "mimeType": "text/plain", "targetLanguageCode": target_lang}
                if source_lang:
                    body["sourceLanguageCode"] = source_lang
                request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                    headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.load(response)
                translations = payload.get("translations", [])
                if len(translations) != len(segments):
                    raise TranslationError("Google returned wrong segment count", "invalid_response")
                rows = [{"id": s["id"], "text": html.unescape(row.get("translatedText", ""))} for s, row in zip(segments, translations)]
                return _restore_rows(rows, maps)
            except TranslationError:
                raise
            except urllib.error.HTTPError as exc:
                code = "auth" if exc.code in {401, 403} else "quota" if exc.code == 429 else "invalid_request" if exc.code < 500 else "transient"
                if api_key and exc.code in {401, 403}:
                    auth_exc = exc
                else:
                    raise TranslationError(f"Google Translation HTTP {exc.code}", code, exc.code >= 500) from exc
            except Exception as exc:
                auth_exc = exc

        # Option 2: Fallback to Cloud Translation v2 using API Key if configured
        if api_key:
            try:
                url = f"https://translation.googleapis.com/language/translate/v2?key={api_key}"
                body = {"q": contents, "format": "text", "target": target_lang}
                if source_lang:
                    body["source"] = source_lang
                request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.load(response)
                translations = payload.get("data", {}).get("translations", [])
                if len(translations) != len(segments):
                    raise TranslationError("Google returned wrong segment count", "invalid_response")
                rows = [{"id": s["id"], "text": html.unescape(row.get("translatedText", ""))} for s, row in zip(segments, translations)]
                return _restore_rows(rows, maps)
            except TranslationError:
                raise
            except urllib.error.HTTPError as exc:
                code = "auth" if exc.code in {401, 403} else "quota" if exc.code == 429 else "invalid_request" if exc.code < 500 else "transient"
                raise TranslationError(f"Google Translation HTTP {exc.code}", code, exc.code >= 500) from exc
            except Exception as exc:
                raise TranslationError(str(exc), "transient", True) from exc

        if auth_exc:
            raise TranslationError(str(auth_exc), "transient", True) from auth_exc
        if not project:
            raise TranslationError("GOOGLE_CLOUD_PROJECT is not configured", "auth")


class HybridTranslationProvider(TranslationProvider):
    name, cloud = "hybrid", True
    def __init__(self, google=None, local=None):
        self.google=google or GoogleTranslationProvider(); self.local=local or LocalTranslationProvider()
    def set_cancel_event(self, event):
        super().set_cancel_event(event)
        self.google.set_cancel_event(event)
        self.local.set_cancel_event(event)
    def capability(self):
        google, local=self.google.capability(),self.local.capability()
        return {"provider":self.name,"cloud":True,"available":google["available"] and local["available"],
                "languages":LANGUAGES,"model":f"{google.get('model')} + {local.get('model')}","components":{"google":google,"local":local}}
    def preflight(self):
        self.google.preflight()
        self.local.preflight()
        return self.capability()
    def translate(self, segments, config, glossary):
        baseline=self.google.translate(segments,config,glossary)
        by_id={row["id"]:row["text"] for row in baseline}
        polished=[{**segment,"baseline_text":by_id[segment["id"]]} for segment in segments]
        protected,maps=_protect_segments(polished,glossary,baseline=True,protect_critical=False)
        if getattr(self, "cancel_event", None) is not None and self.cancel_event.is_set():
            raise TranslationError("Translation cancelled", "cancelled")
        content=self.local.client.generate(_generation_prompt(self.local.client,protected,config,glossary,baseline=True),temperature=0,max_tokens=4000)
        result=_restore_rows(_parse_response(content,[s["id"] for s in segments]),maps)
        for row in result: row["baseline_text"]=by_id[row["id"]]
        return result


def get_provider(name: str) -> TranslationProvider:
    local_specs = {
        "local_api": ("Local LLM API", "api", None, False),
        "cli_codex": ("Codex CLI", "cli", "codex", True),
        "cli_gemini": ("Gemini CLI", "cli", "gemini", True),
        "cli_agy": ("AGY CLI", "cli", "agy", True),
        "cli_claude": ("Claude CLI", "cli", "claude", True),
        "cli_lms": ("LM Studio CLI", "cli", "lms", False),
    }
    if name == "local":
        return LocalTranslationProvider()
    if name in local_specs:
        label, transport, adapter, cloud = local_specs[name]
        return LocalTranslationProvider(name=name, label=label, transport=transport,
                                        cli_provider=adapter, cloud=cloud)
    return {"google":GoogleTranslationProvider,"hybrid":HybridTranslationProvider}[name]()


def capabilities() -> Dict[str, Any]:
    labels = {
        "local":"Local AI ตาม Settings",
        "local_api":"Local LLM API", "cli_codex":"Codex CLI", "cli_gemini":"Gemini CLI",
        "cli_agy":"AGY CLI", "cli_claude":"Claude CLI", "cli_lms":"LM Studio CLI",
        "google":"Google Cloud Translation", "hybrid":"Hybrid: Google → AI ตาม Settings",
    }
    def inspect(name, provider):
        try:
            item=provider.capability(); item.setdefault("label",labels[name]); return item
        except Exception as exc:
            return {"provider":name,"label":labels[name],"available":False,
                    "cloud":name in {"google","hybrid"},"languages":LANGUAGES,"error":str(exc)}
    # API and configured Local AI may involve loopback health checks. Run once in parallel.
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix="translation-capability") as executor:
        futures = {
            "local_api": executor.submit(inspect,"local_api",get_provider("local_api")),
            "local": executor.submit(inspect,"local",get_provider("local")),
            "google": executor.submit(inspect,"google",get_provider("google")),
        }
        checked={name:future.result() for name,future in futures.items()}
    result=[checked["local_api"]]
    for name in ("cli_codex","cli_gemini","cli_agy","cli_claude","cli_lms"):
        route=get_provider(name)
        installed=bool(getattr(route.client,"cli_path",None))
        result.append({"provider":name,"label":labels[name],"available":installed,"cloud":route.cloud,
                       "transport":"cli","cli_adapter":route.client.cli_provider,
                       "model":route.client.model,"languages":LANGUAGES,
                       "error":None if installed else f"AI CLI '{route.client.cli_provider}' not found",
                       "readiness":"preflight_on_start"})
    result.append(checked["google"])
    local=checked["local"]; google=checked["google"]
    result.append({"provider":"hybrid","label":labels["hybrid"],"available":google.get("available") and local.get("available"),
                   "cloud":True,"languages":LANGUAGES,"model":f"{google.get('model')} + {local.get('model')}",
                   "components":{"google":google,"local":local},
                   "error":google.get("error") or local.get("error")})
    return {"providers":result,"styles":STYLE_RULES,"prompt_version":"10.0.0"}
