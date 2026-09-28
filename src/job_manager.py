"""
Phase 4: Job Manager & Subprocess Worker Supervisor.
Coordinates execution of worker subprocesses:
1. Enforces max concurrency (default 1 for local OCR engine).
2. Spawns worker as a dedicated Python subprocess (FastAPI never loads OneOCR DLL).
3. Detects worker crashes (non-zero exit code), updates DB state, and recovers gracefully.
4. Manages queue transitions from queued -> running -> completed/partial/failed/cancelled.
"""
import os
import sys
import time
import subprocess
import threading
from typing import Dict, Optional, List, Tuple, Any
from collections import deque

from src.database import JobDatabase
from src.job_models import JobStatus, PageStatus


class JobManager:
    """
    Subprocess-based job scheduler and supervisor.
    """

    def __init__(
        self,
        db_path: str = "data/jobs.db",
        output_dir: str = "data/jobs",
        max_concurrent_workers: int = 1,
    ):
        self.db_path = db_path
        self.output_dir = output_dir
        self.max_concurrent_workers = max_concurrent_workers
        self.db = JobDatabase(db_path=db_path)

        self._lock = threading.RLock()
        self._active_processes: Dict[str, subprocess.Popen] = {}  # job_id -> Popen
        self._active_attempts: Dict[str, int] = {}
        self._queue: deque = deque()  # list of job_ids queued
        self._stop_event = threading.Event()
        self._supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        self._supervisor_thread.start()

    def ensure_started(self):
        """
        Ensures the background supervisor thread is alive and running.
        If it was stopped, clears stop event and restarts supervisor.
        """
        with self._lock:
            if self._stop_event.is_set() or not self._supervisor_thread.is_alive():
                self._stop_event.clear()
                self._supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
                self._supervisor_thread.start()

    def enqueue_job(
        self,
        job_id: str,
        enable_ai: bool = True,
        retry_mode: str = "failed_only",
        simulate_crash_at_page: Optional[int] = None,
        simulate_write_failure_at_page: Optional[int] = None,
        simulate_ai_failure: bool = False,
    ) -> bool:
        """
        Enqueues a job for background processing.
        """
        self.ensure_started()
        with self._lock:
            # If an existing process has already exited, reap it immediately
            if job_id in self._active_processes:
                proc = self._active_processes[job_id]
                if proc.poll() is not None:
                    self._active_processes.pop(job_id, None)
                    self._active_attempts.pop(job_id, None)
                else:
                    return False

            # Check if job is already waiting in queue
            if any(item["job_id"] == job_id for item in self._queue):
                return False

            self._queue.append({
                "job_id": job_id,
                "enable_ai": enable_ai,
                "retry_mode": retry_mode,
                "simulate_crash_at_page": simulate_crash_at_page,
                "simulate_write_failure_at_page": simulate_write_failure_at_page,
                "simulate_ai_failure": simulate_ai_failure,
            })
            self.db.update_job_status(job_id, JobStatus.QUEUED)
            return True

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancels a queued or currently executing job.
        """
        with self._lock:
            # 1. If in queue, remove immediately
            queued_item = None
            for item in list(self._queue):
                if item["job_id"] == job_id:
                    queued_item = item
                    self._queue.remove(item)
                    break

            if queued_item:
                self.db.mark_job_cancelled(job_id, error_message="Cancelled while queued")
                return True

            # 2. If actively running, signal cancellation in DB and terminate process
            if job_id in self._active_processes:
                self.db.mark_job_cancelled(job_id, error_message="Cancelled by user")
                proc = self._active_processes.get(job_id)
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                return True

            # Check if job exists in DB
            job = self.db.get_job_status(job_id)
            if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                self.db.mark_job_cancelled(job_id, error_message="Cancelled by user")
                return True

            return False

    def get_queue_info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_workers": len(self._active_processes),
                "queued_jobs": len(self._queue),
                "active_job_ids": list(self._active_processes.keys()),
                "queued_job_ids": [item["job_id"] for item in self._queue],
                "max_concurrency": self.max_concurrent_workers,
            }

    def _spawn_worker_subprocess(self, task: Dict[str, Any]):
        job_id = task["job_id"]
        job = self.db.get_job_status(job_id)
        if not job:
            return

        attempt = job.current_attempt
        cmd = [
            sys.executable,
            "-m", "src.worker_process",
            "--job-id", job_id,
            "--db-path", self.db_path,
            "--output-dir", self.output_dir,
            "--attempt", str(attempt),
            "--retry-mode", task.get("retry_mode", "failed_only"),
        ]

        cmd.extend(["--enable-ai", "true" if task.get("enable_ai", True) else "false"])
        if task.get("simulate_crash_at_page") is not None:
            cmd.extend(["--simulate-crash-at-page", str(task["simulate_crash_at_page"])])
        if task.get("simulate_write_failure_at_page") is not None:
            cmd.extend(["--simulate-write-failure-at-page", str(task["simulate_write_failure_at_page"])])
        if task.get("simulate_ai_failure", False):
            cmd.append("--simulate-ai-failure")

        # Spawn subprocess redirecting to attempt log file to avoid pipe buffer deadlocks
        job_dir = os.path.abspath(os.path.join(self.output_dir, job_id))
        os.makedirs(job_dir, exist_ok=True)
        log_path = os.path.join(job_dir, f"worker_attempt_{attempt}.log")
        log_f = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
        )
        log_f.close()

        with self._lock:
            self._active_processes[job_id] = proc
            self._active_attempts[job_id] = attempt

    def _supervisor_loop(self):
        """
        Background loop monitoring active workers and scheduling queued jobs.
        """
        while not self._stop_event.is_set():
            time.sleep(0.1)

            # 1. Check active processes
            finished_jobs = []
            with self._lock:
                for job_id, proc in list(self._active_processes.items()):
                    ret_code = proc.poll()
                    if ret_code is not None:
                        finished_jobs.append((job_id, ret_code))

            for job_id, exit_code in finished_jobs:
                with self._lock:
                    proc = self._active_processes.pop(job_id, None)
                    attempt = self._active_attempts.pop(job_id, 1)


                # If worker terminated with non-zero exit code (e.g. crash)
                if exit_code != 0:
                    current_job = self.db.get_job_status(job_id)
                    if current_job and current_job.status not in (JobStatus.CANCELLED, JobStatus.COMPLETED):
                        # Determine if some pages were saved
                        completed = current_job.completed_pages
                        st = JobStatus.PARTIAL if completed > 0 else JobStatus.FAILED
                        err_msg = f"Worker process crashed (exit code {exit_code})"
                        self.db.update_job_status(job_id, st, error_message=err_msg)
                        self.db.finalize_attempt(job_id, attempt, st, error_message=err_msg)

            # 2. Schedule from queue if slots available
            with self._lock:
                while len(self._active_processes) < self.max_concurrent_workers and len(self._queue) > 0:
                    task = self._queue.popleft()
                    self._spawn_worker_subprocess(task)

    def shutdown(self, timeout: float = 2.0):
        self._stop_event.set()
        with self._lock:
            for job_id, proc in list(self._active_processes.items()):
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        self._supervisor_thread.join(timeout=timeout)
