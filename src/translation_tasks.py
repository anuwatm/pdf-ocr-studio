"""Durable background translation jobs with cancellation, retry and revision guards."""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from src.file_utils import atomic_write_json
from src.translation_core import (batch_segments, classify_terms, create_model, digest, export_results,
    load_glossary, read_json, resolve_source, save_model, translation_dir, translation_revision, utc_now,
    validate_translation, ASSEMBLER_VERSION)
from src.translation_providers import TranslationError, capabilities, get_provider

ACTIVE = {"queued", "running", "cancelling"}


def _batch_limit(provider: str) -> int:
    if provider not in {"local","local_api","cli_codex","cli_gemini","cli_agy","cli_claude","cli_lms","hybrid"}: return 8
    try: return max(1,min(8,int(os.getenv("LOCAL_TRANSLATION_BATCH_SEGMENTS","4"))))
    except ValueError: return 4


def _target_language_mismatch(segments, target_language):
    text=" ".join(str(s.get("translated_text") or "") for s in segments if s.get("status") not in {"preserved","unresolved"})
    if len(re.findall(r"[A-Za-z\u0E00-\u0E7F\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]",text))<40:return False
    base=str(target_language).split("-",1)[0].lower()
    patterns={"th":r"[\u0E00-\u0E7F]","zh":r"[\u3400-\u9FFF]","ja":r"[\u3040-\u30FF\u3400-\u9FFF]","ko":r"[\uAC00-\uD7AF]",
              "en":r"[A-Za-z]","de":r"[A-Za-zÀ-ÿ]","fr":r"[A-Za-zÀ-ÿ]","es":r"[A-Za-zÀ-ÿ]","vi":r"[A-Za-zÀ-ỹ]","id":r"[A-Za-z]","ms":r"[A-Za-z]"}
    return bool(base in patterns and not re.search(patterns[base],text))


def estimate(files_dir: str, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    model = create_model(files_dir, job_id, config)
    characters = sum(len(s["source_text"]) for s in model["segments"] if s["status"] != "preserved")
    provider = model["config"]["provider"]
    multiplier = 2 if provider == "hybrid" else 1
    cloud = (provider in {"cli_codex","cli_gemini","cli_agy","cli_claude","google","hybrid"} or
             (provider == "local" and get_provider("local").cloud))
    # Informational estimate only. Billing price must be configured by the operator.
    price_per_million = float(os.getenv("GOOGLE_TRANSLATION_PRICE_PER_MILLION_CHARS", "0") or 0)
    cost = characters * multiplier / 1_000_000 * price_per_million if provider in {"google","hybrid"} else 0
    batch_limit=_batch_limit(provider)
    return {"characters":characters,"billable_characters":characters*multiplier,"batch_count":len(batch_segments(model["segments"],max_segments=batch_limit)),
            "estimated_cost":round(cost,6),"currency":"USD","cloud":cloud,
            "source_revision":model["source_revision"],"glossary_revision":model["glossary_revision"]}


class TranslationTasks:
    def __init__(self, db, job_manager, output_dir: str):
        self.db, self.job_manager, self.output_dir = db, job_manager, output_dir
        self._lock, self._tasks = threading.RLock(), {}

    def _progress_path(self, job_id): return os.path.join(translation_dir(self.output_dir,job_id),"progress.json")
    def _model_path(self, job_id): return os.path.join(translation_dir(self.output_dir,job_id),"translation.json")
    def _write_state(self, job_id, state): atomic_write_json(self._progress_path(job_id),state)

    def is_active(self, job_id):
        with self._lock: return bool(self._tasks.get(job_id) and self._tasks[job_id]["state"]["status"] in ACTIVE)

    def start(self, job_id: str, config: Dict[str, Any], resume: bool = False) -> Dict[str, Any]:
        with self._lock:
            if self.is_active(job_id): return self.status(job_id)
            if not self.db.get_job_status(job_id): raise ValueError("Job not found")
            preview = estimate(self.output_dir,job_id,config)
            if preview["cloud"] and not config.get("cloud_consent"):
                raise ValueError("Cloud privacy consent is required")
            provider = get_provider(config.get("provider", ""))
            if hasattr(provider, "preflight"):
                try:
                    provider.preflight()
                except Exception as exc:
                    raise ValueError(str(exc)) from exc
            capability = provider.capability()
            if not capability.get("available"):
                raise ValueError(capability.get("error") or "Provider unavailable")
            model=create_model(self.output_dir,job_id,config)
            if resume:
                old=read_json(self._model_path(job_id)); old_by_id={s["id"]:s for s in old.get("segments",[])}
                glossary=load_glossary(self.output_dir,job_id)["entries"]
                for segment in model["segments"]:
                    saved=old_by_id.get(segment["id"])
                    saved_status=saved.get("status") if saved else None
                    preservation_matches=(saved_status!="preserved" or segment.get("status")=="preserved")
                    if saved and saved.get("source_text")==segment["source_text"] and preservation_matches and saved_status in {"translated","manual-final","preserved","flagged_for_human_review"}:
                        segment.update(saved)
                        if segment.get("status") in {"translated","flagged_for_human_review"}:
                            segment["warnings"]=validate_translation(segment["source_text"],segment.get("translated_text") or "",
                                                                       glossary,model["config"]["target_language"])
                            segment["status"]="flagged_for_human_review" if segment["warnings"] else "translated"
            batch_limit=_batch_limit(model["config"]["provider"])
            batches=batch_segments(model["segments"],max_segments=batch_limit)
            now=time.time(); task_id=os.urandom(12).hex()
            state={"schema_version":"10.0","task_id":task_id,"job_id":job_id,"status":"queued","stage":"queued",
                   "started_at":now,"updated_at":now,"completed_batches":0,"batch_count":len(batches),
                   "completed_segments":sum(s["status"] in {"manual-final","preserved","translated"} for s in model["segments"]),
                   "total_segments":len(model["segments"]),"characters":preview["characters"],"error":None}
            task={"state":state,"cancel":threading.Event(),"model":model,"batches":batches}
            self._tasks[job_id]=task; save_model(self.output_dir,job_id,model); self._write_state(job_id,state)
            thread=threading.Thread(target=self._run,args=(job_id,task),daemon=True); task["thread"]=thread; thread.start()
            return self.status(job_id)

    def _update(self,job_id,task,**changes):
        with self._lock:
            task["state"].update(changes,updated_at=time.time()); self._write_state(job_id,task["state"])

    def _run(self,job_id,task):
        model=task["model"]; config=model["config"]; provider_name=config["provider"]
        needs_ai=provider_name not in {"google"}; acquired=False
        try:
            if needs_ai:
                acquired=self.job_manager.ai_lock.acquire(blocking=False)
                if not acquired: raise TranslationError("Local AI กำลังทำงานอื่น กรุณาลองใหม่","busy",True)
            provider=get_provider(provider_name)
            if hasattr(provider, "preflight"):
                try:
                    provider.preflight()
                except Exception as exc:
                    raise TranslationError(str(exc), "unavailable") from exc
            capability=provider.capability()
            if not capability.get("available"): raise TranslationError(capability.get("error") or "Provider unavailable","unavailable")
            glossary=load_glossary(self.output_dir,job_id)["entries"]
            self._update(job_id,task,status="running",stage="translating",provider=provider_name,model=capability.get("model"))
            segment_map={s["id"]:s for s in model["segments"]}
            batches=[batch for batch in task["batches"] if any(segment_map[s["id"]]["status"] not in {"translated","manual-final"} for s in batch)]
            for index,batch in enumerate(batches,1):
                if task["cancel"].is_set():
                    model["status"]="cancelled"; save_model(self.output_dir,job_id,model)
                    self._update(job_id,task,status="cancelled",stage="cancelled"); return
                result=None
                for attempt in range(3):
                    try: result=provider.translate(batch,config,glossary); break
                    except TranslationError as exc:
                        if not exc.retryable or attempt==2: raise
                        time.sleep((0.25,1.0,2.0)[attempt])
                result_by_id={row["id"]:row for row in result or []}
                if set(result_by_id)!=set(s["id"] for s in batch): raise TranslationError("Batch ID mismatch","invalid_response")
                for source_segment in batch:
                    segment=segment_map[source_segment["id"]]; row=result_by_id[segment["id"]]
                    target=row["text"]
                    if "\x00" in target or len(target)>max(20_000,len(segment["source_text"])*8+1000):
                        raise TranslationError("Provider returned invalid segment size or content","invalid_response")
                    segment["baseline_text"]=row.get("baseline_text") or (target if provider_name=="google" else None)
                    segment["translated_text"]=target
                    if not segment.get("manual_edited"): segment["final_text"]=target
                    segment["warnings"]=validate_translation(segment["source_text"],target,glossary,config["target_language"])
                    segment["term_states"]=classify_terms(segment["source_text"],target,glossary)
                    segment["status"]=("manual-final" if segment.get("manual_edited") else
                                       "flagged_for_human_review" if segment["warnings"] else "translated")
                    segment["provenance"]={"provider":provider_name,"model":capability.get("model"),
                                           "transport":capability.get("transport"),
                                           "cli_adapter":capability.get("cli_adapter"),"prompt_version":"10.0.0"}
                save_model(self.output_dir,job_id,model)
                self._update(job_id,task,completed_batches=index,
                    completed_segments=sum(s["status"] in {"translated","manual-final","preserved"} for s in model["segments"]))
            if _target_language_mismatch(model["segments"],config["target_language"]):
                candidate=next((s for s in model["segments"] if s.get("status") not in {"preserved","unresolved"}),None)
                if candidate:
                    candidate["warnings"].append("target_language_mismatch")
                    if not candidate.get("manual_edited"):candidate["status"]="flagged_for_human_review"
            _,_,current_source=resolve_source(self.output_dir,job_id,model["source_variant"])
            current_glossary=load_glossary(self.output_dir,job_id).get("revision")
            if current_source!=model.get("source_revision") or current_glossary!=model.get("glossary_revision"):
                raise TranslationError("Translation source or glossary changed during the task","stale")
            if model.get("translation_units"):
                seg_by_id = {s["id"]: s for s in model["segments"]}
                for unit in model["translation_units"]:
                    u_segs = [seg_by_id[sid] for sid in unit.get("source_segment_ids", []) if sid in seg_by_id]
                    if u_segs:
                        head_seg = u_segs[0]
                        unit["status"] = (
                            "flagged_for_human_review" if any(s.get("status") == "flagged_for_human_review" for s in u_segs)
                            else "manual-final" if any(s.get("status") == "manual-final" for s in u_segs)
                            else "translated" if all(s.get("status") in {"translated", "manual-final", "preserved"} for s in u_segs)
                            else "queued"
                        )
                        unit["warnings"] = list(dict.fromkeys(w for s in u_segs for w in s.get("warnings", [])))
                        unit["translated_text"] = head_seg.get("translated_text")
                        unit["final_text"] = head_seg.get("final_text")
            flagged=sum(s["status"] in {"flagged_for_human_review","unresolved"} or bool(s.get("warnings"))
                        for s in model["segments"])
            model["status"]="partial" if flagged else "completed"; model["completed_at"]=utc_now()
            if not flagged: export_results(self.output_dir,job_id,model)
            save_model(self.output_dir,job_id,model)
            self._update(job_id,task,status=model["status"],stage="review" if flagged else "completed",flagged_segments=flagged)
            latency = max(0.0, time.time() - task["state"]["started_at"])
            audit={"task_id":task["state"]["task_id"],"provider":provider_name,"model":capability.get("model"),
                   "transport":capability.get("transport"),"cli_adapter":capability.get("cli_adapter"),
                   "cli_version":capability.get("cli_version"),"prompt_version":"10.0.0","exit_code":0,
                   "latency_seconds":round(latency,3),"characters":task["state"]["characters"],
                   "input_hash":digest([s.get("source_text") for s in model["segments"]]),
                   "output_hash":digest([s.get("final_text") or s.get("translated_text") for s in model["segments"]]),
                   "validation_result":{
                       "total_segments":len(model["segments"]),
                       "flagged_segments":flagged,
                       "valid":flagged==0,
                       "warnings":list({w.split(":")[0] for s in model["segments"] for w in s.get("warnings",[])}),
                   },
                   "started_at":task["state"]["started_at"],"completed_at":time.time(),
                   "cloud_consent":bool(config.get("cloud_consent")),"credential_recorded":False}
            atomic_write_json(os.path.join(translation_dir(self.output_dir,job_id),"audit.json"),audit)
        except Exception as exc:
            model["status"]="cancelled" if task["cancel"].is_set() else "failed"; save_model(self.output_dir,job_id,model)
            self._update(job_id,task,status=model["status"],stage=model["status"],error=str(exc),
                         error_code=getattr(exc,"code","error"),retryable=bool(getattr(exc,"retryable",False)))
        finally:
            if acquired: self.job_manager.ai_lock.release()

    def status(self,job_id):
        with self._lock:
            task=self._tasks.get(job_id); state=dict(task["state"]) if task else read_json(self._progress_path(job_id))
        if not state: return {"job_id":job_id,"status":"idle"}
        if not task and state.get("status") in ACTIVE:
            state.update(status="failed",stage="failed",error="Server restarted during translation; use retry to resume",retryable=True)
        end=time.time() if state.get("status") in ACTIVE else state.get("updated_at",time.time())
        state["elapsed_seconds"]=max(0,end-state.get("started_at",end)); return state

    def cancel(self,job_id):
        with self._lock:
            task=self._tasks.get(job_id)
            if task and task["state"]["status"] in ACTIVE:
                task["cancel"].set(); self._update(job_id,task,status="cancelling",stage="cancelling")
        return self.status(job_id)

    def result(self,job_id):
        model=read_json(self._model_path(job_id))
        if not model: return model
        reasons=[]
        try:
            _,_,current_source=resolve_source(self.output_dir,job_id,model.get("source_variant","auto"))
            if current_source!=model.get("source_revision"): reasons.append("source_revision_changed")
        except (FileNotFoundError,ValueError): reasons.append("source_unavailable")
        if load_glossary(self.output_dir,job_id).get("revision")!=model.get("glossary_revision"):
            reasons.append("glossary_revision_changed")
        if model.get("assembler_version") != ASSEMBLER_VERSION:
            reasons.append("assembler_version_changed")
        model["stale"]=bool(reasons); model["stale_reasons"]=reasons
        return model

    def save_final(self,job_id:str,edits:List[Dict[str,Any]],base_revision:str):
        model=self.result(job_id)
        if not model: raise FileNotFoundError("Translation result not found")
        if model.get("stale"): raise ValueError("Conflict: translation source or glossary changed")
        if model.get("translation_revision")!=base_revision: raise ValueError("Conflict: translation revision changed")
        by_id={s["id"]:s for s in model["segments"]}
        for edit in edits:
            segment=by_id.get(str(edit.get("id","")))
            if not segment: raise ValueError("Unknown translation segment")
            if segment.get("status")=="unresolved": raise ValueError("Unresolved table cell cannot be published")
            text=str(edit.get("text", "")); segment.update(final_text=text,manual_edited=True,status="manual-final")
            segment["warnings"]=validate_translation(segment["source_text"],text,load_glossary(self.output_dir,job_id)["entries"],
                                                       model["config"]["target_language"])
        flagged=sum(s.get("status")=="unresolved" or bool(s.get("warnings")) for s in model["segments"])
        model["status"]="partial" if flagged else "completed"; model["translation_revision"]=translation_revision(model)
        if not flagged: export_results(self.output_dir,job_id,model)
        return save_model(self.output_dir,job_id,model)

    def shutdown(self):
        with self._lock:
            for task in self._tasks.values(): task["cancel"].set()
