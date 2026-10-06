"""
Phase 6: Data Retention & Cleanup Service.
Strictly coordinates retention lifecycle with Worker and JobManager:
1. Defines retention policy (default TTL: 24h / 86400s).
2. Calculates age strictly from 'updated_at' of finalized jobs (completed, partial, failed, cancelled).
3. Strictly protects active running or queued jobs — never deletes in-progress jobs.
4. Coordinated deletion: cleans filesystem artifacts first, then purges DB rows (CASCADE).
5. Prevents late-arriving results from resurrecting deleted jobs (coordinating with worker checks).
"""
from src.job_artifact_guard import guard_artifacts, is_artifact_busy
import os
import shutil
import time
import re
from typing import List, Dict, Any, Optional

from src.database import JobDatabase
from src.job_models import JobStatus

# Default retention configuration (24 hours)
DEFAULT_RETENTION_SECONDS: float = float(os.getenv("RETENTION_SECONDS", "86400.0"))
JOB_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def safe_job_dir(output_base_dir: str, job_id: str) -> str:
    """Return a job directory only when it is a direct child of output_base_dir."""
    if not re.fullmatch(JOB_ID_PATTERN, job_id):
        raise ValueError("Invalid job path")

    base_dir = os.path.realpath(output_base_dir)
    job_dir = os.path.realpath(os.path.join(base_dir, job_id))
    try:
        is_child = os.path.commonpath([base_dir, job_dir]) == base_dir
    except ValueError:
        # Windows raises ValueError for paths on different drives.
        is_child = False
    if not is_child or job_dir == base_dir:
        raise ValueError("Invalid job path")
    return job_dir


class RetentionPolicy:
    """
    Encapsulates rules for data retention and cleanup cycles.
    """
    def __init__(self, retention_seconds: float = DEFAULT_RETENTION_SECONDS):
        self.retention_seconds = retention_seconds

    def is_job_active(self, job_status: str, job_id: str, job_manager: Optional[Any] = None) -> bool:
        """
        Determines if a job is actively executing or queued, and must NOT be deleted.
        """
        if is_artifact_busy(job_id, getattr(job_manager, "output_dir", "files")):
            return True
        if job_status in (JobStatus.RUNNING.value, JobStatus.QUEUED.value):
            return True
        if job_manager:
            q_info = job_manager.get_queue_info()
            if job_id in q_info.get("active_job_ids", []) or job_id in q_info.get("queued_job_ids", []):
                return True
            tasks = getattr(job_manager, "html_ai_tasks", None)
            if tasks is not None and tasks.is_active(job_id):
                return True
        return False


@guard_artifacts
def delete_single_job(
    job_id: str,
    db: JobDatabase,
    output_base_dir: str = "data/jobs",
    job_manager: Optional[Any] = None,
    force: bool = False,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Explicitly deletes a single job and its artifacts from disk and database.
    If the job is currently actively running and force=False, refuses deletion.
    """
    # Validate before consulting the database so an unsafe ID never reaches any
    # deletion branch, including the orphaned-directory path.
    job_dir = safe_job_dir(output_base_dir, job_id)
    job = db.get_job_status(job_id)
    if not job:
        # Check if orphaned folder exists on disk
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=not strict)
            return {"job_id": job_id, "deleted": True, "details": "Removed orphaned directory"}
        return {"job_id": job_id, "deleted": False, "details": "Job not found"}

    # If running, check force
    if job.status == JobStatus.RUNNING:
        if not force:
            raise ValueError(f"Job {job_id} is currently running. Cancel before deletion.")
        if job_manager:
            job_manager.cancel_job(job_id)
            time.sleep(0.2)
    elif job.status == JobStatus.QUEUED:
        if job_manager:
            job_manager.cancel_job(job_id)

    # 1. Remove disk directory and all artifacts (source, images, results, logs)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=not strict)

    # 2. Purge from database
    db.delete_job(job_id)

    return {
        "job_id": job_id,
        "deleted": True,
        "details": f"Job {job_id} artifacts and database records purged successfully.",
    }


def cleanup_expired_jobs(
    db: JobDatabase,
    output_base_dir: str = "data/jobs",
    retention_seconds: Optional[float] = None,
    job_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes a cleanup cycle:
    1. Identifies jobs whose updated_at exceeds retention_seconds.
    2. Excludes active (running/queued) jobs.
    3. Purges filesystem files and database records.
    4. Returns summary of cleaned jobs.
    """
    ttl = retention_seconds if retention_seconds is not None else DEFAULT_RETENTION_SECONDS
    policy = RetentionPolicy(retention_seconds=ttl)

    # Query expired candidates
    expired_ids = db.get_expired_jobs(max_age_seconds=ttl)
    cleaned_jobs: List[str] = []
    skipped_jobs: List[str] = []
    # The candidate query excludes these jobs. Report them explicitly so a
    # zero-result cleanup is distinguishable from a failed deletion.
    if ttl == 0:
        with db.read_connection() as conn:
            skipped_jobs = [row["job_id"] for row in conn.execute(
                "SELECT job_id FROM jobs WHERE status IN (?, ?)",
                (JobStatus.RUNNING.value, JobStatus.QUEUED.value),
            ).fetchall()]

    for jid in expired_ids:
        job = db.get_job_status(jid)
        if not job:
            continue

        # Double check active protection
        if is_artifact_busy(jid, output_base_dir) or policy.is_job_active(job.status.value, jid, job_manager):
            skipped_jobs.append(jid)
            continue

        # Safely delete
        res = delete_single_job(jid, db, output_base_dir, job_manager=job_manager, force=False)
        if res.get("deleted"):
            cleaned_jobs.append(jid)

    return {
        "retention_seconds": ttl,
        "cleaned_count": len(cleaned_jobs),
        "cleaned_jobs": cleaned_jobs,
        "skipped_active_jobs": skipped_jobs,
    }
