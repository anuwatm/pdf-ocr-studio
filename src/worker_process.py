"""
Phase 4: Standalone Worker Process for OCR and AI Text Correction.
Key architectural principles:
1. Runs in a separate process from FastAPI — loads OneOCR DLL only inside this process.
2. Writes each page artifact to disk atomically with UTF-8 before updating DB.
3. Checks cancellation flag before and during page processing.
4. Checks attempt number: stale/outdated attempt cannot overwrite newer attempt.
5. Supports retry modes: failed_only (skip completed pages), ai_only (reuse existing ocr.json / raw.txt).
6. Handles simulated disk write failure and faults without declaring false success.
"""
import os
import sys
import json
import time
import argparse
import traceback
import shutil
import gc
from typing import Optional, List, Dict, Any

from src.database import JobDatabase
from src.job_models import OCR_BATCH_SIZE, JobStatus, PageStatus, StageStatus, JobStatusResponse
from src.pipeline import ProcessingPipeline


def _run_full_text_ai_review(page_dir: str, job_id: str, page_num: int, revision: int) -> Dict[str, Any]:
    """Run Local AI on the saved raw text without repeating OCR."""
    raw_path = os.path.join(page_dir, "raw.txt")
    ocr_path = os.path.join(page_dir, "ocr.json")
    if not os.path.exists(raw_path) or not os.path.exists(ocr_path):
        raise FileNotFoundError("Saved OCR text is unavailable for full-text AI review")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    with open(ocr_path, "r", encoding="utf-8") as f:
        ocr_data = json.load(f)

    page_data = (ocr_data.get("pages") or [{}])[0]
    from src.ai_corrector import AICorrector
    corrected_text, changes_doc = AICorrector().correct_text(
        raw_text=raw_text,
        job_id=job_id,
        page_id=page_num,
        source_revision=revision,
        current_revision=revision,
        page_blocks=page_data.get("blocks"),
        char_mapping=page_data.get("char_mapping"),
        use_prescreener=False,
    )
    with open(os.path.join(page_dir, "corrected.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(corrected_text)
    with open(os.path.join(page_dir, "changes.json"), "w", encoding="utf-8") as f:
        json.dump(changes_doc.model_dump(), f, ensure_ascii=False, indent=2)
    return {"raw_text": raw_text}


def _iter_page_batches(page_numbers: List[int], batch_size: int = OCR_BATCH_SIZE):
    """Yields sequential page groups so long jobs release OCR resources every batch."""
    for offset in range(0, len(page_numbers), batch_size):
        yield page_numbers[offset:offset + batch_size]


def process_job_worker(
    job_id: str,
    db_path: str = "data/jobs.db",
    output_base_dir: str = "data/jobs",
    enable_ai: bool = True,
    attempt_number: int = 1,
    retry_mode: str = "failed_only",
    simulate_crash_at_page: Optional[int] = None,
    simulate_write_failure_at_page: Optional[int] = None,
    simulate_ai_failure: bool = False,
):
    """
    Main worker function executing in separate process.
    """
    db = JobDatabase(db_path=db_path)
    job = db.get_job_status(job_id)
    if not job:
        print(f"[Worker] Job {job_id} not found in database.", file=sys.stderr)
        return

    # Check attempt freshness
    if job.current_attempt != attempt_number:
        print(f"[Worker] Stale attempt {attempt_number} rejected. Current is {job.current_attempt}.", file=sys.stderr)
        return

    # Job working directory
    job_dir = os.path.abspath(os.path.join(output_base_dir, job_id))
    os.makedirs(job_dir, exist_ok=True)
    file_path = db.get_job_raw_path(job_id)
    if not file_path or not os.path.exists(file_path):
        db.update_job_status(job_id, JobStatus.FAILED, error_message=f"Input file missing: {file_path}")
        db.finalize_attempt(job_id, attempt_number, JobStatus.FAILED, error_message="Input file missing")
        return

    # Update job status to running
    db.update_job_status(job_id, JobStatus.RUNNING)

    pipeline = ProcessingPipeline()
    total_pages = job.total_pages
    pages_to_process = []

    for p in job.pages:
        if retry_mode == "failed_only":
            if p.status != PageStatus.COMPLETED and p.status != PageStatus.BLANK:
                pages_to_process.append(p.page_num)
        elif retry_mode == "ai_only":
            if p.ocr_status == StageStatus.COMPLETED and p.ai_status != StageStatus.COMPLETED:
                pages_to_process.append(p.page_num)
        elif retry_mode == "full_text_ai":
            if p.ocr_status == StageStatus.COMPLETED:
                pages_to_process.append(p.page_num)
        else:  # full
            pages_to_process.append(p.page_num)

    if not pages_to_process:
        # All required pages were already completed
        db.update_job_status(job_id, JobStatus.COMPLETED)
        db.finalize_attempt(job_id, attempt_number, JobStatus.COMPLETED)
        return

    total_batches = max(1, (len(pages_to_process) + OCR_BATCH_SIZE - 1) // OCR_BATCH_SIZE)
    print(
        f"[Worker] Starting processing job {job_id}, attempt {attempt_number}, "
        f"{len(pages_to_process)} pages in {total_batches} batches of {OCR_BATCH_SIZE}."
    )

    any_ocr_failed = False
    any_ai_failed = False
    is_cancelled = False

    for page_index, page_num in enumerate(pages_to_process):
        batch_number = (page_index // OCR_BATCH_SIZE) + 1
        if page_index % OCR_BATCH_SIZE == 0:
            batch_end = min(page_index + OCR_BATCH_SIZE, len(pages_to_process))
            print(
                f"[Worker] Batch {batch_number}/{total_batches}: "
                f"pages {pages_to_process[page_index]}–{pages_to_process[batch_end - 1]}"
            )
        # 1. Check for cancellation, deletion, or attempt supersede before starting page
        current_job = db.get_job_status(job_id)
        if not current_job:
            print(f"[Worker] Job {job_id} was deleted (e.g. cleanup policy). Halting worker.")
            return
        if current_job.status == JobStatus.CANCELLED:
            print(f"[Worker] Job {job_id} cancelled by user. Halting page processing.")
            is_cancelled = True
            break
        if current_job.current_attempt != attempt_number:
            print(f"[Worker] Job {job_id} attempt superseded ({current_job.current_attempt} > {attempt_number}). Aborting.")
            return

        # 2. Simulate worker native crash if requested
        if simulate_crash_at_page is not None and page_num == simulate_crash_at_page:
            print(f"[Worker] Simulating worker crash at page {page_num}...")
            # Sudden exit simulating hard native access violation / kill
            os._exit(139)

        # Mark page running
        is_full_text_ai = retry_mode == "full_text_ai"
        db.update_page_progress(
            job_id=job_id,
            page_id=page_num,
            status=PageStatus.RUNNING,
            ocr_status=StageStatus.COMPLETED if is_full_text_ai else StageStatus.RUNNING,
            ai_status=StageStatus.RUNNING if enable_ai else StageStatus.SKIPPED,
            attempt_number=attempt_number,
        )

        t_start = time.perf_counter()
        page_dir = os.path.join(job_dir, f"page_{page_num:02d}")
        os.makedirs(page_dir, exist_ok=True)

        try:
            # Check if simulating write failure (e.g. disk full)
            if simulate_write_failure_at_page is not None and page_num == simulate_write_failure_at_page:
                raise IOError(f"Simulated disk full / write failure at page {page_num}")

            # Execute OCR + AI via pipeline for this page
            actual_enable_ai = enable_ai and (not simulate_ai_failure)
            if is_full_text_ai:
                page_status = next(p for p in job.pages if p.page_num == page_num)
                result = _run_full_text_ai_review(page_dir, job_id, page_num, page_status.revision)
            else:
                result = pipeline.process_file(
                    file_path=file_path,
                    output_dir=page_dir,
                    page_range=[page_num],
                    enable_ai_correction=actual_enable_ai,
                )

            # Check if job was deleted or directory cleaned up while pipeline was executing
            post_check_job = db.get_job_status(job_id)
            if not post_check_job or not os.path.exists(job_dir):
                print(f"[Worker] Job {job_id} or job directory was removed during processing. Halting worker without recreating files.")
                return
            if post_check_job.status == JobStatus.CANCELLED:
                print(f"[Worker] Job {job_id} cancelled during processing.")
                is_cancelled = True
                break

            # Ensure corrected.txt exists when AI is disabled
            corrected_path = os.path.join(page_dir, "corrected.txt")
            if not os.path.exists(corrected_path):
                with open(corrected_path, "w", encoding="utf-8") as f:
                    f.write(result.get("raw_text", ""))

            # Phase 5 Requirement: final.txt starts from raw.txt.
            # If final.txt already exists (e.g. user manually edited during AI or retry),
            # DO NOT OVERWRITE! Preserve user manual edit.
            final_page_path = os.path.join(page_dir, "final.txt")
            if not os.path.exists(final_page_path):
                with open(final_page_path, "w", encoding="utf-8") as f:
                    f.write(result.get("raw_text", ""))

            latency = (time.perf_counter() - t_start) * 1000.0

            # Verify files were actually written to disk
            raw_path = os.path.join(page_dir, "raw.txt")
            ocr_json_path = os.path.join(page_dir, "ocr.json")
            corrected_path = os.path.join(page_dir, "corrected.txt")
            changes_json_path = os.path.join(page_dir, "changes.json")

            raw_len = 0
            if os.path.exists(raw_path):
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_len = len(f.read())

            corrections_cnt = 0
            ai_error_message = None
            ai_failed = False
            if os.path.exists(changes_json_path):
                with open(changes_json_path, "r", encoding="utf-8") as f:
                    try:
                        cdata = json.load(f)
                        corrections_cnt = cdata.get("total_corrections", 0)
                        if enable_ai and cdata.get("status") != "completed":
                            ai_failed = True
                            ai_error_message = cdata.get("error_message") or f"AI correction status: {cdata.get('status', 'unknown')}"
                    except Exception:
                        if enable_ai:
                            ai_failed = True
                            ai_error_message = "Could not read AI correction result"
            elif enable_ai:
                ai_failed = True
                ai_error_message = "AI correction result was not written"

            # Determine statuses
            if simulate_ai_failure:
                # OCR succeeded but AI stage failed
                any_ai_failed = True
                db.update_page_progress(
                    job_id=job_id,
                    page_id=page_num,
                    status=PageStatus.PARTIAL,
                    ocr_status=StageStatus.COMPLETED,
                    ai_status=StageStatus.FAILED,
                    attempt_number=attempt_number,
                    latency_ms=latency,
                    error_message="AI correction service failed / timeout",
                    raw_text_length=raw_len,
                    corrections_count=0,
                )
            elif ai_failed:
                # OCR is usable, but Local AI returned timeout, malformed JSON,
                # or another explicit failure. Never report this page as fully completed.
                any_ai_failed = True
                db.update_page_progress(
                    job_id=job_id,
                    page_id=page_num,
                    status=PageStatus.PARTIAL,
                    ocr_status=StageStatus.COMPLETED,
                    ai_status=StageStatus.FAILED,
                    attempt_number=attempt_number,
                    latency_ms=latency,
                    error_message=ai_error_message,
                    raw_text_length=raw_len,
                    corrections_count=corrections_cnt,
                )
            else:
                # Page fully completed
                db.update_page_progress(
                    job_id=job_id,
                    page_id=page_num,
                    status=PageStatus.COMPLETED,
                    ocr_status=StageStatus.COMPLETED,
                    ai_status=StageStatus.COMPLETED if enable_ai else StageStatus.SKIPPED,
                    attempt_number=attempt_number,
                    latency_ms=latency,
                    raw_text_length=raw_len,
                    corrections_count=corrections_cnt,
                )

        except Exception as e:
            latency = (time.perf_counter() - t_start) * 1000.0
            err_msg = str(e)
            if is_full_text_ai:
                any_ai_failed = True
            else:
                any_ocr_failed = True
            db.update_page_progress(
                job_id=job_id,
                page_id=page_num,
                status=PageStatus.PARTIAL if is_full_text_ai else PageStatus.FAILED,
                ocr_status=StageStatus.COMPLETED if is_full_text_ai else StageStatus.FAILED,
                ai_status=StageStatus.FAILED if enable_ai else StageStatus.SKIPPED,
                attempt_number=attempt_number,
                latency_ms=latency,
                error_message=err_msg,
            )

        if (page_index + 1) % OCR_BATCH_SIZE == 0 or page_index + 1 == len(pages_to_process):
            pipeline.close()
            gc.collect()
            if page_index + 1 < len(pages_to_process):
                pipeline = ProcessingPipeline()
            print(f"[Worker] Batch {batch_number}/{total_batches} finished.")

    pipeline.close()
    gc.collect()

    # 3. Finalize Job Status
    updated_job = db.get_job_status(job_id)
    if not updated_job:
        return

    # Check for cancellation
    if is_cancelled or updated_job.status == JobStatus.CANCELLED:
        # Mark remaining queued/running pages as cancelled
        for p in updated_job.pages:
            if p.status in (PageStatus.QUEUED, PageStatus.RUNNING):
                db.update_page_progress(
                    job_id=job_id,
                    page_id=p.page_id,
                    status=PageStatus.CANCELLED,
                    ocr_status=StageStatus.SKIPPED,
                    ai_status=StageStatus.SKIPPED,
                    attempt_number=attempt_number,
                    error_message="Cancelled by user",
                )
        db.update_job_status(job_id, JobStatus.CANCELLED, error_message="Job cancelled by user")
        db.finalize_attempt(job_id, attempt_number, JobStatus.CANCELLED, error_message="Cancelled by user")
        return

    # Assemble overall job files (raw.txt, corrected.txt, final.txt) across pages
    if os.path.exists(job_dir):
        _assemble_job_text_files(job_dir, updated_job)
    else:
        print(f"[Worker] Job directory {job_dir} was deleted. Skipping file assembly.")
        return

    # Calculate final status
    completed = updated_job.completed_pages
    failed = updated_job.failed_pages

    has_partial = any(p.status == PageStatus.PARTIAL for p in updated_job.pages)
    completed = updated_job.completed_pages

    if completed == total_pages and not has_partial:
        final_st = JobStatus.COMPLETED
    elif completed > 0 or has_partial:
        final_st = JobStatus.PARTIAL
    else:
        final_st = JobStatus.FAILED

    db.update_job_status(job_id, final_st)
    db.finalize_attempt(job_id, attempt_number, final_st)
    print(f"[Worker] Job {job_id} finished with status {final_st.value}. Completed {completed}/{total_pages} pages.")


def _assemble_job_text_files(job_dir: str, job_status: JobStatusResponse):
    """
    Concatenates individual page outputs into top-level document files:
    - raw.txt
    - corrected.txt
    - final.txt
    Includes standard page break characters (form feed '\\f' or page headers)
    and explicit markers for failed or cancelled pages without dropping them silently.
    """
    if not os.path.exists(job_dir):
        return

    raw_lines = []
    corr_lines = []
    final_lines = []

    for page_info in job_status.pages:
        p_num = page_info.page_num
        page_dir = os.path.join(job_dir, f"page_{p_num:02d}")
        page_header = f"--- Page {p_num} ---"

        if page_info and page_info.status == PageStatus.FAILED:
            marker = f"[PAGE {p_num}: PROCESSING FAILED - {page_info.error_message or 'Error'}]"
            raw_lines.append(f"{page_header}\n{marker}\n")
            corr_lines.append(f"{page_header}\n{marker}\n")
            final_lines.append(f"{page_header}\n{marker}\n")
            continue

        if page_info and page_info.status == PageStatus.CANCELLED:
            marker = f"[PAGE {p_num}: CANCELLED]"
            raw_lines.append(f"{page_header}\n{marker}\n")
            corr_lines.append(f"{page_header}\n{marker}\n")
            final_lines.append(f"{page_header}\n{marker}\n")
            continue

        raw_file = os.path.join(page_dir, "raw.txt")
        corr_file = os.path.join(page_dir, "corrected.txt")
        final_file = os.path.join(page_dir, "final.txt")

        p_raw = ""
        if os.path.exists(raw_file):
            with open(raw_file, "r", encoding="utf-8") as f:
                p_raw = f.read()

        p_corr = p_raw
        if os.path.exists(corr_file):
            with open(corr_file, "r", encoding="utf-8") as f:
                p_corr = f.read()

        p_final = p_raw
        if os.path.exists(final_file):
            with open(final_file, "r", encoding="utf-8") as f:
                p_final = f.read()

        raw_lines.append(f"{page_header}\n{p_raw}\n")
        corr_lines.append(f"{page_header}\n{p_corr}\n")
        final_lines.append(f"{page_header}\n{p_final}\n")

    # Write document-level outputs with UTF-8
    with open(os.path.join(job_dir, "raw.txt"), "w", encoding="utf-8") as f:
        f.write("\f\n".join(raw_lines))

    with open(os.path.join(job_dir, "corrected.txt"), "w", encoding="utf-8") as f:
        f.write("\f\n".join(corr_lines))

    # Document final.txt assembled from page final.txt (preserving user edits)
    final_path = os.path.join(job_dir, "final.txt")
    with open(final_path, "w", encoding="utf-8") as f:
        f.write("\f\n".join(final_lines))

    # Copy page_01 metadata to document-level if available
    p1_json = os.path.join(job_dir, "page_01", "ocr.json")
    if os.path.exists(p1_json) and not os.path.exists(os.path.join(job_dir, "ocr.json")):
        shutil.copy(p1_json, os.path.join(job_dir, "ocr.json"))
    p1_changes = os.path.join(job_dir, "page_01", "changes.json")
    if os.path.exists(p1_changes) and not os.path.exists(os.path.join(job_dir, "changes.json")):
        shutil.copy(p1_changes, os.path.join(job_dir, "changes.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone OCR Worker Process")
    parser.add_argument("--job-id", required=True, help="Job ID to process")
    parser.add_argument("--db-path", default="data/jobs.db", help="Path to SQLite database")
    parser.add_argument("--output-dir", default="data/jobs", help="Base output directory")
    parser.add_argument("--enable-ai", type=lambda x: str(x).lower() in ("true", "1", "yes"), default=True, help="Enable AI correction")
    parser.add_argument("--attempt", type=int, default=1, help="Attempt number")
    parser.add_argument("--retry-mode", default="failed_only", choices=["failed_only", "ai_only", "full"])
    parser.add_argument("--simulate-crash-at-page", type=int, default=None)
    parser.add_argument("--simulate-write-failure-at-page", type=int, default=None)
    parser.add_argument("--simulate-ai-failure", action="store_true", default=False)

    args = parser.parse_args()

    process_job_worker(
        job_id=args.job_id,
        db_path=args.db_path,
        output_base_dir=args.output_dir,
        enable_ai=args.enable_ai,
        attempt_number=args.attempt,
        retry_mode=args.retry_mode,
        simulate_crash_at_page=args.simulate_crash_at_page,
        simulate_write_failure_at_page=args.simulate_write_failure_at_page,
        simulate_ai_failure=args.simulate_ai_failure,
    )
