"""
Phase 6: Data Retention & Cleanup Service.
Strictly coordinates retention lifecycle with Worker and JobManager:
1. Defines retention policy (default TTL: 24h / 86400s).
2. Calculates age strictly from 'updated_at' of finalized jobs (completed, partial, failed, cancelled).
3. Strictly protects active running or queued jobs — never deletes in-progress jobs.
4. Coordinated deletion: cleans filesystem artifacts first, then purges DB rows (CASCADE).
5. Prevents late-arriving results from resurrecting deleted jobs (coordinating with worker checks).
"""
import os
import shutil
import time
from typing import List, Dict, Any, Optional

from src.database import JobDatabase
from src.job_models import JobStatus

# Default retention configuration (24 hours)
DEFAULT_RETENTION_SECONDS: float = float(os.getenv("RETENTION_SECONDS", "86400.0"))


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
        if job_status in (JobStatus.RUNNING.value, JobStatus.QUEUED.value):
            return True
        if job_manager:
            q_info = job_manager.get_queue_info()
            if job_id in q_info.get("active_job_ids", []) or job_id in q_info.get("queued_job_ids", []):
                return True
        return False


def delete_single_job(
    job_id: str,
    db: JobDatabase,
    output_base_dir: str = "data/jobs",
    job_manager: Optional[Any] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Explicitly deletes a single job and its artifacts from disk and database.
    If the job is currently actively running and force=False, refuses deletion.
    """
    job = db.get_job_status(job_id)
    if not job:
        # Check if orphaned folder exists on disk
        job_dir = os.path.abspath(os.path.join(output_base_dir, job_id))
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
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
    job_dir = os.path.abspath(os.path.join(output_base_dir, job_id))
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=True)

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

    for jid in expired_ids:
        job = db.get_job_status(jid)
        if not job:
            continue

        # Double check active protection
        if policy.is_job_active(job.status.value, jid, job_manager):
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
