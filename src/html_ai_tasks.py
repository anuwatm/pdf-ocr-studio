"""Background AI HTML exports with durable progress and cooperative cancellation."""
import json
import os
import threading
import time
import uuid

from src.cleanup_service import safe_job_dir
from src.file_utils import atomic_write_json
from src.html_exporter import generate_ai_html, generate_basic_html
from src.llm_client import LocalLLMClient


ACTIVE_STATES = {"running", "cancelling"}


class HtmlAiTasks:
    def __init__(self, db, job_manager, output_dir):
        self.db = db
        self.job_manager = job_manager
        self.output_dir = output_dir
        self._lock = threading.RLock()
        self._tasks = {}

    def _path(self, job_id):
        return os.path.join(safe_job_dir(self.output_dir, job_id), "export", "ai_progress.json")

    def is_active(self, job_id):
        with self._lock:
            task = self._tasks.get(job_id)
            return bool(task and task["state"]["status"] in ACTIVE_STATES)

    def start(self, job_id):
        with self._lock:
            if self.is_active(job_id):
                return self.status(job_id)
            if not self.db.get_job_status(job_id):
                raise ValueError("Job not found")
            # Reserve the same lock as synchronous AI exports before dispatch.
            if self.job_manager.is_ai_in_use() or not self.job_manager.ai_lock.acquire(blocking=False):
                raise ValueError("Local AI กำลังทำงานอื่น กรุณารอให้งานนั้นเสร็จก่อน")
            now = time.time()
            task = {"cancel": threading.Event(), "state": {
                "task_id": uuid.uuid4().hex, "job_id": job_id, "status": "running",
                "stage": "checking_ai", "started_at": now, "updated_at": now,
                "stage_started_at": now, "chunk_count": 0, "completed_chunks": 0,
                "current_chunk": 0, "timeout_seconds": 0,
            }}
            self._tasks[job_id] = task
            try:
                atomic_write_json(self._path(job_id), task["state"])
                thread = threading.Thread(target=self._run, args=(job_id, task), daemon=True)
                task["thread"] = thread
                thread.start()
            except Exception:
                self._tasks.pop(job_id, None)
                self.job_manager.ai_lock.release()
                raise
            return self.status(job_id)

    def _update(self, job_id, task, **changes):
        with self._lock:
            state = task["state"]
            now = time.time()
            if changes.get("stage", state["stage"]) != state["stage"]:
                changes["stage_started_at"] = now
            if task["cancel"].is_set() and changes.get("status", "running") == "running":
                changes["status"] = "cancelling"
            state.update(changes, updated_at=now)
            if self.db.get_job_status(job_id):
                atomic_write_json(self._path(job_id), state)

    def _run(self, job_id, task):
        try:
            client = LocalLLMClient(max_retries=0)
            self._update(job_id, task, timeout_seconds=client.timeout)
            health = client.check_health()
            if task["cancel"].is_set():
                self._update(job_id, task, status="cancelled", stage="cancelled")
                return
            if health.get("status") not in ("connected", "healthy"):
                generate_basic_html(job_id, files_dir=self.output_dir)
                self._update(job_id, task, status="failed", stage="failed",
                             error=health.get("error") or "Local AI is offline")
                return
            self._update(job_id, task, stage="preparing")
            _, meta = generate_ai_html(
                job_id, files_dir=self.output_dir, llm_client=client,
                progress_callback=lambda **changes: self._update(job_id, task, **changes),
                cancel_requested=task["cancel"].is_set,
            )
            result = meta.get("validator_status")
            status = "completed" if result == "passed" else "cancelled" if result == "cancelled" else "failed"
            if task["cancel"].is_set() and status != "completed":
                status = "cancelled"
            self._update(job_id, task, status=status, stage=status, meta=meta,
                         ai_applied=result == "passed",
                         error=meta.get("error") or meta.get("validator_reason") or meta.get("message")
                         or ("ไม่พบข้อความสำหรับสร้าง HTML" if result == "no_units" else None))
        except Exception as exc:
            # Keep in-memory diagnostics even if the disk itself cannot be written.
            try:
                status = "cancelled" if task["cancel"].is_set() else "failed"
                self._update(job_id, task, status=status, stage=status, error=str(exc))
            except Exception:
                with self._lock:
                    task["state"].update(status="failed", stage="failed", error=str(exc), updated_at=time.time())
        finally:
            self.job_manager.ai_lock.release()

    def status(self, job_id):
        with self._lock:
            task = self._tasks.get(job_id)
            if task:
                state = dict(task["state"])
            else:
                try:
                    with open(self._path(job_id), encoding="utf-8") as handle:
                        state = json.load(handle)
                except FileNotFoundError:
                    return {"job_id": job_id, "status": "idle"}
                if state.get("status") in ACTIVE_STATES:
                    state.update(status="failed", stage="failed",
                                 error="Server restarted during AI export; please retry")
            now = time.time()
            end = state.get("updated_at", now) if state["status"] not in ACTIVE_STATES else now
            state["elapsed_seconds"] = max(0, end - state["started_at"])
            state["waiting_seconds"] = max(0, now - state["stage_started_at"]) if state["stage"] == "waiting_ai" else 0
            state["last_update_seconds"] = max(0, now - state["updated_at"])
            return state

    def cancel(self, job_id):
        with self._lock:
            task = self._tasks.get(job_id)
            if task and task["state"]["status"] in ACTIVE_STATES:
                task["cancel"].set()
                self._update(job_id, task, status="cancelling")
            return self.status(job_id)

    def shutdown(self):
        with self._lock:
            for task in self._tasks.values():
                task["cancel"].set()
