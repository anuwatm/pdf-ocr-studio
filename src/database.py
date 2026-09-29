"""
Phase 4: SQLite Database & State Persistence.
Strictly adheres to:
1. WAL journal mode (PRAGMA journal_mode=WAL)
2. Busy timeout (PRAGMA busy_timeout = 5000)
3. Short, bounded transactions
4. Crash recovery detection on startup
5. Lock contention handling with retry
"""
import sqlite3
import os
import time
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from contextlib import contextmanager

from src.job_models import OCR_BATCH_SIZE, JobStatus, PageStatus, StageStatus, ReviewStatus, PageProgress, JobStatusResponse


class DatabaseLockTimeoutError(Exception):
    """
    Raised when SQLite database lock contention times out after retries,
    notifying the caller of failure and requiring retry without silently dropping data.
    """
    pass


class RevisionConflictError(Exception):
    """
    Raised when an edit is attempted against an outdated page revision.
    Prevents silent overwrite when multiple tabs or sessions edit concurrently.
    """
    pass


def get_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobDatabase:
    """
    Thread-safe SQLite database manager for jobs, pages, and attempts.
    Features:
    - WAL journal mode
    - Busy timeout (5000ms)
    - Short bounded transactions with exponential backoff on lock contention
    - Explicit DatabaseLockTimeoutError on lock timeout (failure/retry notification)
    - Never silently drops modifications
    """

    def __init__(self, db_path: str = "data/jobs.db", busy_timeout_ms: int = 5000):
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def transaction(self, timeout: Optional[float] = None, max_retries: int = 5, base_delay: float = 0.05):
        """
        Executes a short, bounded SQLite write transaction with automatic retry
        on transient lock contention (sqlite3.OperationalError: database is locked / busy).
        If lock contention cannot be resolved within retries/timeout,
        raises DatabaseLockTimeoutError with explicit failure/retry notification.
        Never drops modifications silently.
        """
        t_timeout = timeout if timeout is not None else (self.busy_timeout_ms / 1000.0)
        start_time = time.time()
        conn = None
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=t_timeout)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(f"PRAGMA busy_timeout={int(t_timeout * 1000)};")
                conn.execute("PRAGMA foreign_keys=ON;")
                yield conn
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                err_str = str(e).lower()
                if "locked" in err_str or "busy" in err_str:
                    if conn:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                    elapsed = time.time() - start_time
                    if attempt < max_retries - 1 and elapsed < t_timeout:
                        time.sleep(base_delay * (2 ** attempt))
                        continue
                    raise DatabaseLockTimeoutError(
                        f"SQLite lock contention timed out after {attempt + 1} attempts ({elapsed:.2f}s). "
                        "Database is busy/locked. Action: failure/retry required."
                    ) from e
                else:
                    if conn:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                    raise
            except Exception:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                raise
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    @contextmanager
    def read_connection(self, timeout: Optional[float] = None):
        """
        Context manager for read-only queries with busy timeout.
        """
        t_timeout = timeout if timeout is not None else (self.busy_timeout_ms / 1000.0)
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=t_timeout)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(f"PRAGMA busy_timeout={int(t_timeout * 1000)};")
            yield conn
        except sqlite3.OperationalError as e:
            err_str = str(e).lower()
            if "locked" in err_str or "busy" in err_str:
                raise DatabaseLockTimeoutError(
                    f"SQLite read lock timed out. Database is busy/locked. Action: failure/retry required."
                ) from e
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _get_connection(self) -> sqlite3.Connection:
        """Deprecated compatibility method, delegates to standard connect."""
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                total_pages INTEGER NOT NULL,
                status TEXT NOT NULL,
                review_status TEXT NOT NULL,
                current_attempt INTEGER NOT NULL DEFAULT 1,
                enable_ai INTEGER NOT NULL DEFAULT 1,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                job_id TEXT NOT NULL,
                page_id INTEGER NOT NULL,
                page_num INTEGER NOT NULL,
                status TEXT NOT NULL,
                ocr_status TEXT NOT NULL,
                ai_status TEXT NOT NULL,
                attempt_number INTEGER NOT NULL DEFAULT 1,
                latency_ms REAL,
                error_message TEXT,
                raw_text_length INTEGER NOT NULL DEFAULT 0,
                corrections_count INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 1,
                has_manual_edit INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (job_id, page_id),
                FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            );
            """)

            # Dynamic migration for existing DB
            cursor.execute("PRAGMA table_info(pages);")
            existing_cols = [r["name"] for r in cursor.fetchall()]
            if "revision" not in existing_cols:
                cursor.execute("ALTER TABLE pages ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;")
            if "has_manual_edit" not in existing_cols:
                cursor.execute("ALTER TABLE pages ADD COLUMN has_manual_edit INTEGER NOT NULL DEFAULT 0;")

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                job_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                error_message TEXT,
                PRIMARY KEY (job_id, attempt_number),
                FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            );
            """)

        # Run startup crash recovery
        self.recover_interrupted_jobs()

    def recover_interrupted_jobs(self) -> int:
        """
        Scans for jobs/pages left in 'running' state from a server crash or sudden shutdown.
        Recovers state safely according to policy without declaring false success.
        """
        now = get_iso_now()
        recovered_count = 0
        with self.transaction() as conn:
            cursor = conn.cursor()
            # Find running jobs
            cursor.execute("SELECT job_id, current_attempt FROM jobs WHERE status = ?", (JobStatus.RUNNING.value,))
            running_jobs = cursor.fetchall()

            for rj in running_jobs:
                job_id = rj["job_id"]
                attempt = rj["current_attempt"]
                recovered_count += 1

                # Check page progress
                cursor.execute(
                    "SELECT COUNT(*) as completed FROM pages WHERE job_id = ? AND status = ?",
                    (job_id, PageStatus.COMPLETED.value)
                )
                completed_count = cursor.fetchone()["completed"]

                # Mark uncompleted running pages as failed due to crash
                cursor.execute("""
                    UPDATE pages
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE job_id = ? AND status = ?
                """, (
                    PageStatus.FAILED.value,
                    "Interrupted by server restart or process termination",
                    now,
                    job_id,
                    PageStatus.RUNNING.value
                ))

                # Job status: partial if some pages completed, else failed
                new_status = JobStatus.PARTIAL.value if completed_count > 0 else JobStatus.FAILED.value
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE job_id = ?
                """, (
                    new_status,
                    "Interrupted by server restart or worker crashed",
                    now,
                    job_id
                ))

                # Update attempt
                cursor.execute("""
                    UPDATE attempts
                    SET status = ?, ended_at = ?, error_message = ?
                    WHERE job_id = ? AND attempt_number = ?
                """, (
                    new_status,
                    now,
                    "Interrupted by server restart",
                    job_id,
                    attempt
                ))

        return recovered_count

    def create_job(
        self,
        job_id: str,
        filename: str,
        file_path: str,
        file_size_bytes: int,
        total_pages: int,
        enable_ai: bool = True
    ) -> JobStatusResponse:
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (
                    job_id, filename, file_path, file_size_bytes, total_pages,
                    status, review_status, current_attempt, enable_ai,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, filename, file_path, file_size_bytes, total_pages,
                JobStatus.QUEUED.value, ReviewStatus.UNREVIEWED.value, 1,
                1 if enable_ai else 0, None, now, now
            ))

            # Initialize pages
            page_rows = []
            for p in range(1, total_pages + 1):
                page_rows.append((
                    job_id, p, p, PageStatus.QUEUED.value,
                    StageStatus.PENDING.value, StageStatus.PENDING.value,
                    1, None, None, 0, 0, 1, 0, now
                ))
            cursor.executemany("""
                INSERT INTO pages (
                    job_id, page_id, page_num, status,
                    ocr_status, ai_status, attempt_number,
                    latency_ms, error_message, raw_text_length,
                    corrections_count, revision, has_manual_edit, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, page_rows)

            # Record initial attempt
            cursor.execute("""
                INSERT INTO attempts (job_id, attempt_number, status, started_at)
                VALUES (?, ?, ?, ?)
            """, (job_id, 1, JobStatus.QUEUED.value, now))

        return self.get_job_status(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        with self.read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            job_row = cursor.fetchone()
            if not job_row:
                return None

            cursor.execute("""
                SELECT * FROM pages WHERE job_id = ? ORDER BY page_id ASC
            """, (job_id,))
            page_rows = cursor.fetchall()

            pages = []
            completed_pages = 0
            failed_pages = 0
            cancelled_pages = 0

            for p in page_rows:
                st = PageStatus(p["status"])
                if st == PageStatus.COMPLETED or st == PageStatus.BLANK:
                    completed_pages += 1
                elif st == PageStatus.FAILED:
                    failed_pages += 1
                elif st == PageStatus.CANCELLED:
                    cancelled_pages += 1

                p_keys = p.keys()
                pages.append(PageProgress(
                    page_id=p["page_id"],
                    page_num=p["page_num"],
                    status=st,
                    ocr_status=StageStatus(p["ocr_status"]),
                    ai_status=StageStatus(p["ai_status"]),
                    attempt_number=p["attempt_number"],
                    latency_ms=p["latency_ms"],
                    error_message=p["error_message"],
                    raw_text_length=p["raw_text_length"],
                    corrections_count=p["corrections_count"],
                    revision=p["revision"] if "revision" in p_keys else 1,
                    has_manual_edit=bool(p["has_manual_edit"]) if "has_manual_edit" in p_keys else False,
                ))

            total_batches = max(1, (job_row["total_pages"] + OCR_BATCH_SIZE - 1) // OCR_BATCH_SIZE)
            next_page_index = next(
                (index for index, page in enumerate(pages) if page.status in (PageStatus.QUEUED, PageStatus.RUNNING)),
                None,
            )
            current_batch = total_batches if next_page_index is None else (next_page_index // OCR_BATCH_SIZE) + 1

            return JobStatusResponse(
                job_id=job_row["job_id"],
                status=JobStatus(job_row["status"]),
                review_status=ReviewStatus(job_row["review_status"]),
                filename=job_row["filename"],
                file_size_bytes=job_row["file_size_bytes"],
                total_pages=job_row["total_pages"],
                batch_size=OCR_BATCH_SIZE,
                total_batches=total_batches,
                current_batch=current_batch,
                completed_pages=completed_pages,
                failed_pages=failed_pages,
                cancelled_pages=cancelled_pages,
                current_attempt=job_row["current_attempt"],
                enable_ai=bool(job_row["enable_ai"]),
                error_message=job_row["error_message"],
                created_at=job_row["created_at"],
                updated_at=job_row["updated_at"],
                pages=pages,
            )

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        review_status: Optional[ReviewStatus] = None,
    ):
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            if review_status:
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, review_status = ?, updated_at = ?
                    WHERE job_id = ?
                """, (status.value, error_message, review_status.value, now, job_id))
            else:
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE job_id = ?
                """, (status.value, error_message, now, job_id))

    def configure_job_for_start(self, job_id: str, page_start: int, page_end: int, enable_ai: bool) -> bool:
        """Locks a queued job to a contiguous, user-selected PDF page range."""
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT total_pages, status FROM jobs WHERE job_id = ?", (job_id,))
            job = cursor.fetchone()
            if not job or job["status"] != JobStatus.QUEUED.value:
                return False
            if page_start < 1 or page_end < page_start or page_end > job["total_pages"]:
                return False

            selected_count = page_end - page_start + 1

            cursor.execute(
                "DELETE FROM pages WHERE job_id = ? AND (page_num < ? OR page_num > ?)",
                (job_id, page_start, page_end),
            )
            cursor.execute(
                """
                UPDATE jobs
                SET total_pages = ?, enable_ai = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (selected_count, 1 if enable_ai else 0, now, job_id),
            )
        return True

    def mark_job_cancelled(self, job_id: str, error_message: str = "Cancelled by user"):
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pages
                SET status = ?, error_message = ?, updated_at = ?
                WHERE job_id = ? AND status IN (?, ?)
            """, (PageStatus.CANCELLED.value, error_message, now, job_id, PageStatus.QUEUED.value, PageStatus.RUNNING.value))

            cursor.execute("""
                UPDATE jobs
                SET status = ?, error_message = ?, updated_at = ?
                WHERE job_id = ?
            """, (JobStatus.CANCELLED.value, error_message, now, job_id))

    def update_page_progress(
        self,
        job_id: str,
        page_id: int,
        status: PageStatus,
        ocr_status: StageStatus,
        ai_status: StageStatus,
        attempt_number: int,
        latency_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        raw_text_length: int = 0,
        corrections_count: int = 0,
    ):
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pages
                SET status = ?, ocr_status = ?, ai_status = ?,
                    attempt_number = ?, latency_ms = ?, error_message = ?,
                    raw_text_length = ?, corrections_count = ?, updated_at = ?
                WHERE job_id = ? AND page_id = ?
            """, (
                status.value, ocr_status.value, ai_status.value,
                attempt_number, latency_ms, error_message,
                raw_text_length, corrections_count, now,
                job_id, page_id
            ))

    def increment_attempt(self, job_id: str) -> int:
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_attempt, review_status FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            new_attempt = (row["current_attempt"] + 1) if row else 1

            # If job was reviewed, revert to in_review on new attempt/retry per spec:
            # "แก้ข้อความหรือเปลี่ยน attempt หลัง reviewed แล้วกลับ in_review"
            new_review_st = row["review_status"] if row else ReviewStatus.UNREVIEWED.value
            if new_review_st == ReviewStatus.REVIEWED.value:
                new_review_st = ReviewStatus.IN_REVIEW.value

            cursor.execute("""
                UPDATE jobs SET current_attempt = ?, review_status = ?, updated_at = ? WHERE job_id = ?
            """, (new_attempt, new_review_st, now, job_id))

            cursor.execute("""
                INSERT INTO attempts (job_id, attempt_number, status, started_at)
                VALUES (?, ?, ?, ?)
            """, (job_id, new_attempt, JobStatus.QUEUED.value, now))

            return new_attempt

    def finalize_attempt(self, job_id: str, attempt_number: int, status: JobStatus, error_message: Optional[str] = None):
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE attempts
                SET status = ?, ended_at = ?, error_message = ?
                WHERE job_id = ? AND attempt_number = ?
            """, (status.value, now, error_message, job_id, attempt_number))

    def get_job_raw_path(self, job_id: str) -> Optional[str]:
        with self.read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return row["file_path"] if row else None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT job_id, filename, file_size_bytes, total_pages, status,
                       review_status, current_attempt, created_at, updated_at
                FROM jobs ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_page_revision(self, job_id: str, page_id: int) -> int:
        with self.read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT revision FROM pages WHERE job_id = ? AND page_id = ?", (job_id, page_id))
            row = cursor.fetchone()
            return row["revision"] if row and "revision" in row.keys() else 1

    def save_page_edit(
        self,
        job_id: str,
        page_id: int,
        source_revision: int,
        edited_text: str,
        output_dir: str = "data/jobs",
        check_conflict: bool = False,
    ) -> Dict[str, Any]:
        """
        Saves user manual edit to page final.txt with revision conflict checking.
        - If check_conflict and source_revision != current_revision: raises RevisionConflictError.
        - Increments revision to current_revision + 1.
        - Sets has_manual_edit = 1.
        - Automatically transitions job review_status to 'in_review'.
        - Writes page final.txt and reassembles document-level final.txt.
        - Never silently overwrites.
        """
        import json
        now = get_iso_now()
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT revision, has_manual_edit FROM pages WHERE job_id = ? AND page_id = ?", (job_id, page_id))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Page {page_id} not found in job {job_id}")

            current_rev = row["revision"]
            if check_conflict and source_revision != current_rev:
                raise RevisionConflictError(
                    f"Conflict detected: page {page_id} is currently at revision {current_rev}, "
                    f"but client submitted edit based on revision {source_revision}. "
                    "Another edit was saved. Edits will not be silently overwritten."
                )

            new_revision = current_rev + 1

            # Update page revision & manual edit flag
            cursor.execute("""
                UPDATE pages
                SET revision = ?, has_manual_edit = 1, updated_at = ?
                WHERE job_id = ? AND page_id = ?
            """, (new_revision, now, job_id, page_id))

            # When user edits, transition job review_status to in_review
            new_review_st = ReviewStatus.IN_REVIEW.value
            cursor.execute("""
                UPDATE jobs SET review_status = ?, updated_at = ? WHERE job_id = ?
            """, (new_review_st, now, job_id))

        # Write final.txt to page directory
        job_dir = os.path.abspath(os.path.join(output_dir, job_id))
        page_dir = os.path.join(job_dir, f"page_{page_id:02d}")
        os.makedirs(page_dir, exist_ok=True)
        final_file = os.path.join(page_dir, "final.txt")
        with open(final_file, "w", encoding="utf-8") as f:
            f.write(edited_text)

        # Reassemble document-level final.txt
        self._reassemble_job_final(job_id, output_dir)

        return {
            "page_id": page_id,
            "new_revision": new_revision,
            "review_status": new_review_st,
            "message": "Manual edit saved successfully",
        }

    def _reassemble_job_final(self, job_id: str, output_dir: str = "data/jobs"):
        job = self.get_job_status(job_id)
        if not job:
            return
        job_dir = os.path.abspath(os.path.join(output_dir, job_id))
        include_page_numbers = True
        try:
            with open(os.path.join(job_dir, "assembly_options.json"), "r", encoding="utf-8") as f:
                include_page_numbers = bool(json.load(f).get("include_page_numbers", True))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

        def page_chunk(header: str, text: str) -> str:
            return f"{header}\n{text}\n" if include_page_numbers else f"{text}\n"

        def remove_internal_page_header(text: str, page_num: int) -> str:
            header = f"--- Page {page_num} ---"
            if text.startswith(header):
                return text[len(header):].lstrip("\r\n")
            return text

        final_lines = []
        for p in job.pages:
            p_num = p.page_num
            p_dir = os.path.join(job_dir, f"page_{p_num:02d}")
            header = f"--- Page {p_num} ---"
            if p.status == PageStatus.FAILED:
                final_lines.append(page_chunk(header, f"[PAGE {p_num}: PROCESSING FAILED - {p.error_message or 'Error'}]"))
            elif p.status == PageStatus.CANCELLED:
                final_lines.append(page_chunk(header, f"[PAGE {p_num}: CANCELLED]"))
            else:
                p_text = ""
                p_final = os.path.join(p_dir, "final.txt")
                p_corr = os.path.join(p_dir, "corrected.txt")
                p_raw = os.path.join(p_dir, "raw.txt")
                if os.path.exists(p_final):
                    with open(p_final, "r", encoding="utf-8") as f:
                        p_text = f.read()
                elif os.path.exists(p_corr):
                    with open(p_corr, "r", encoding="utf-8") as f:
                        p_text = f.read()
                elif os.path.exists(p_raw):
                    with open(p_raw, "r", encoding="utf-8") as f:
                        p_text = f.read()
                p_text = remove_internal_page_header(p_text, p_num)
                final_lines.append(page_chunk(header, p_text))

        with open(os.path.join(job_dir, "final.txt"), "w", encoding="utf-8") as f:
            f.write("\f\n".join(final_lines))

    def apply_proposal_action(
        self,
        job_id: str,
        page_id: int,
        change_id: str,
        action: str,  # 'accept' or 'revert'
        output_dir: str = "data/jobs",
    ) -> Dict[str, Any]:
        """
        Accepts or reverts an AI proposal for a page.
        - Loads changes.json and updates proposal status ('accepted' / 'rejected' / 'pending').
        - Updates page final.txt with the accepted/reverted text.
        - Increments revision.
        - Reassembles job final.txt.
        - If review_status was 'reviewed', transitions back to 'in_review'.
        """
        import json
        job_dir = os.path.abspath(os.path.join(output_dir, job_id))
        page_dir = os.path.join(job_dir, f"page_{page_id:02d}")
        changes_path = os.path.join(page_dir, "changes.json")
        raw_path = os.path.join(page_dir, "raw.txt")
        final_path = os.path.join(page_dir, "final.txt")

        if not os.path.exists(changes_path):
            raise FileNotFoundError(f"changes.json not found for job {job_id} page {page_id}")

        with open(changes_path, "r", encoding="utf-8") as f:
            changes_data = json.load(f)

        target_item = None
        for item in changes_data.get("corrections", []):
            if item.get("change_id") == change_id:
                target_item = item
                break

        if not target_item:
            raise ValueError(f"Correction proposal '{change_id}' not found")

        # Load current text
        if os.path.exists(final_path):
            with open(final_path, "r", encoding="utf-8") as f:
                current_text = f.read()
        elif os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                current_text = f.read()
        else:
            current_text = ""

        orig = target_item.get("original_text", "")
        corr = target_item.get("corrected_text", "")

        if action == "accept":
            target_item["status"] = "accepted"
            if orig in current_text:
                new_text = current_text.replace(orig, corr, 1)
            else:
                new_text = current_text
        elif action == "revert":
            target_item["status"] = "rejected"
            if corr in current_text:
                new_text = current_text.replace(corr, orig, 1)
            else:
                new_text = current_text
        else:
            raise ValueError(f"Unknown action: {action}")

        # Update counters
        acc = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "accepted")
        rej = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "rejected")
        pend = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "pending")
        changes_data["accepted_corrections"] = acc
        changes_data["rejected_corrections"] = rej
        changes_data["pending_corrections"] = pend

        with open(changes_path, "w", encoding="utf-8") as f:
            json.dump(changes_data, f, ensure_ascii=False, indent=2)

        curr_rev = self.get_page_revision(job_id, page_id)
        res = self.save_page_edit(
            job_id=job_id,
            page_id=page_id,
            source_revision=curr_rev,
            edited_text=new_text,
            output_dir=output_dir,
        )
        res["target_item"] = target_item
        res["final_text"] = new_text
        return res

    def apply_all_proposals(
        self,
        job_id: str,
        page_id: int,
        action: str,  # 'accept' or 'revert'
        output_dir: str = "data/jobs",
    ) -> Dict[str, Any]:
        """
        Accepts or reverts all proposals for a page in batch.
        """
        import json
        job_dir = os.path.abspath(os.path.join(output_dir, job_id))
        page_dir = os.path.join(job_dir, f"page_{page_id:02d}")
        changes_path = os.path.join(page_dir, "changes.json")
        raw_path = os.path.join(page_dir, "raw.txt")
        corr_path = os.path.join(page_dir, "corrected.txt")

        if not os.path.exists(changes_path):
            raise FileNotFoundError(f"changes.json not found for job {job_id} page {page_id}")

        with open(changes_path, "r", encoding="utf-8") as f:
            changes_data = json.load(f)

        if action == "accept":
            if os.path.exists(corr_path):
                with open(corr_path, "r", encoding="utf-8") as f:
                    new_text = f.read()
            else:
                new_text = ""
            for item in changes_data.get("corrections", []):
                item["status"] = "accepted"
        else:
            if os.path.exists(raw_path):
                with open(raw_path, "r", encoding="utf-8") as f:
                    new_text = f.read()
            else:
                new_text = ""
            for item in changes_data.get("corrections", []):
                item["status"] = "rejected"

        acc = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "accepted")
        rej = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "rejected")
        pend = sum(1 for c in changes_data.get("corrections", []) if c.get("status") == "pending")
        changes_data["accepted_corrections"] = acc
        changes_data["rejected_corrections"] = rej
        changes_data["pending_corrections"] = pend

        with open(changes_path, "w", encoding="utf-8") as f:
            json.dump(changes_data, f, ensure_ascii=False, indent=2)

        curr_rev = self.get_page_revision(job_id, page_id)
        res = self.save_page_edit(
            job_id=job_id,
            page_id=page_id,
            source_revision=curr_rev,
            edited_text=new_text,
            output_dir=output_dir,
        )
        res["final_text"] = new_text
        return res

    def delete_job(self, job_id: str) -> bool:
        """
        Deletes a job and its associated pages and attempts from the database.
        Returns True if a job was deleted, False if job did not exist.
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,))
            if not cursor.fetchone():
                return False
            cursor.execute("DELETE FROM attempts WHERE job_id = ?", (job_id,))
            cursor.execute("DELETE FROM pages WHERE job_id = ?", (job_id,))
            cursor.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            return True

    def get_expired_jobs(self, max_age_seconds: float) -> List[str]:
        """
        Finds jobs that have expired based on max_age_seconds from updated_at,
        excluding jobs currently in 'running' or 'queued' state.
        """
        now = datetime.now(timezone.utc)
        expired_ids = []
        with self.read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_id, updated_at FROM jobs WHERE status NOT IN (?, ?)",
                (JobStatus.RUNNING.value, JobStatus.QUEUED.value),
            )
            rows = cursor.fetchall()
            for r in rows:
                jid = r["job_id"]
                up_str = r["updated_at"]
                try:
                    up_dt = datetime.fromisoformat(up_str)
                    if up_dt.tzinfo is None:
                        up_dt = up_dt.replace(tzinfo=timezone.utc)
                    age = (now - up_dt).total_seconds()
                    if age >= max_age_seconds:
                        expired_ids.append(jid)
                except Exception:
                    pass
        return expired_ids
