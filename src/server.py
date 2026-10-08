"""
Phase 4: FastAPI Application & REST Endpoints.
Implements:
- POST /api/upload (file validation, page limit, encrypted PDF rejection, path traversal protection)
- POST /api/jobs/{job_id}/start
- GET /api/jobs/{job_id}/status
- POST /api/jobs/{job_id}/cancel
- POST /api/jobs/{job_id}/retry
- GET /api/jobs/{job_id}/download/{file_type}
- PUT /api/jobs/{job_id}/pages/{page_id}/edit
- POST /api/jobs/{job_id}/review
- GET /api/health
"""
import os
import re
import uuid
import shutil
import zipfile
import tempfile
import time
import json
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Annotated
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Path, status, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import pypdfium2 as pdfium

from src.config import HOST, PORT, LOCALHOST_ONLY, get_llm_config, update_llm_config

from src.database import JobDatabase, DatabaseLockTimeoutError, RevisionConflictError
from src.job_manager import JobManager
from src.job_models import (
    OCR_BATCH_SIZE, JobStatus, PageStatus, ReviewStatus,
    JobCreateResponse, JobStartRequest, JobStatusResponse,
    JobRetryRequest, PageEditRequest, PageEditResponse, LocalLLMConfigRequest
)

# Configuration defaults
MAX_FILE_SIZE_BYTES = 300 * 1024 * 1024  # 300 MB
DEFAULT_DB_PATH = "data/jobs.db"
DEFAULT_OUTPUT_DIR = "files"

# Global managers
db = JobDatabase(db_path=DEFAULT_DB_PATH)
job_manager = JobManager(db_path=DEFAULT_DB_PATH, output_dir=DEFAULT_OUTPUT_DIR)
from src.html_ai_tasks import HtmlAiTasks
html_ai_tasks = HtmlAiTasks(db, job_manager, DEFAULT_OUTPUT_DIR)
job_manager.html_ai_tasks = html_ai_tasks

JOB_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
JobId = Annotated[str, Path(pattern=JOB_ID_PATTERN, description="Unique job identifier")]


def sanitize_filename(filename: str) -> str:
    """
    Prevents path traversal attacks by extracting only the safe basename
    and rejecting dangerous characters or path navigation sequences.
    """
    if not filename:
        return "uploaded_file"
    # Strip null bytes and directory components
    clean = filename.replace("\x00", "").replace("\\", "/").split("/")[-1]
    # Remove leading dots to prevent hidden or parent directory references
    clean = re.sub(r"^\.+", "", clean)
    clean = re.sub(r"[^\w\.\-\_ ]", "_", clean)
    return clean if clean else "file"


def is_path_traversal(target_path: str, base_dir: str) -> bool:
    """
    Checks if target_path escapes outside base_dir.
    """
    target = os.path.realpath(target_path)
    base = os.path.realpath(base_dir)
    try:
        return os.path.commonpath([base, target]) != base or target == base
    except ValueError:
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover interrupted jobs
    db.recover_interrupted_jobs()
    yield
    # Shutdown
    html_ai_tasks.shutdown()
    job_manager.shutdown()


app = FastAPI(
    title="Local Thai OCR & Correction API",
    version="4.0.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = {
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
    "http://testserver",
    f"http://testserver:{PORT}",
}
ALLOWED_HOSTS = {
    f"127.0.0.1:{PORT}",
    f"localhost:{PORT}",
    f"[::1]:{PORT}",
    "testserver",
    f"testserver:{PORT}",
}
if PORT == 80:
    ALLOWED_ORIGINS.update({"http://127.0.0.1", "http://localhost"})
    ALLOWED_HOSTS.update({"127.0.0.1", "localhost", "::1", "[::1]"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def enforce_loopback_only(request: Request, call_next):
    """
    Phase 6: Verifies loopback restriction.
    Ensures that when running in localhost mode, external/non-loopback requests are blocked.
    """
    if LOCALHOST_ONLY:
        client_host = request.client.host if request.client else "unknown"
        allowed_client_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
        if client_host not in allowed_client_hosts:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Access denied: server is bound to localhost loopback only. Client IP '{client_host}' is blocked."},
            )
        # Check Host header: strictly bound to configured PORT or testserver (Bug 2)
        host = (request.headers.get("host") or "").lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden host"})
        # Check Origin header: strictly bound to configured PORT or testserver (Bug 2)
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden origin"})
    return await call_next(request)


@app.exception_handler(DatabaseLockTimeoutError)
async def handle_database_lock_timeout(request, exc: DatabaseLockTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": f"Database lock timeout: {exc}. Action: failure/retry required. Edits are not silently discarded.",
            "retryable": True,
        },
        headers={"Retry-After": "1"},
    )



@app.exception_handler(RevisionConflictError)
async def handle_revision_conflict(request, exc: RevisionConflictError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": str(exc),
            "conflict": True,
            "message": "พบข้อขัดแย้ง: หน้านี้มีการบันทึกแก้ไขจากแท็บอื่นแล้ว ระบบจะไม่เขียนทับข้อมูลโดยไม่แจ้ง กรุณารีเฟรชเพื่อดูเนื้อหาล่าสุด",
        },
    )


@app.get("/api/health")
def health_check():
    q_info = job_manager.get_queue_info()
    return {
        "status": "healthy",
        "service": "Local Thai OCR Web",
        "phase": 4,
        "queue": q_info,
    }


@app.get("/api/ai/status")
def get_ai_status():
    from src.llm_client import LocalLLMClient
    client = LocalLLMClient()
    return client.check_health()


def _validated_local_llm_config(payload: LocalLLMConfigRequest) -> dict:
    """Allows configuration only for a loopback OpenAI-compatible endpoint."""
    base_url = payload.base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local LLM Base URL ต้องเป็น http(s)://127.0.0.1, localhost หรือ ::1 เท่านั้น",
        )
    return {
        "base_url": base_url,
        "model": payload.model.strip(),
        "timeout": payload.timeout,
        "api_key": payload.api_key,
    }


@app.get("/api/ai/config")
def get_ai_config():
    """Returns editable Local LLM settings without returning the secret key."""
    return get_llm_config()


@app.post("/api/ai/config/test")
def test_ai_config(payload: LocalLLMConfigRequest):
    """Tests an unsaved loopback-only Local LLM configuration."""
    from src.llm_client import LocalLLMClient
    config = _validated_local_llm_config(payload)
    client = LocalLLMClient(**config)
    return client.check_health()


@app.put("/api/ai/config")
def save_ai_config(payload: LocalLLMConfigRequest):
    """Saves Local LLM settings to .env and applies them to new AI jobs immediately."""
    config = _validated_local_llm_config(payload)
    return update_llm_config(**config)


def _inspect_pdf_page_count(file_path: str) -> int:
    pdf_doc = pdfium.PdfDocument(file_path)
    try:
        return len(pdf_doc)
    finally:
        pdf_doc.close()


@app.post("/api/upload", response_model=JobCreateResponse)
async def upload_file(
    file: UploadFile = File(...),
    max_pages_limit: Optional[int] = Form(None),
    max_size_limit: Optional[int] = Form(None),
):
    """
    Uploads a document into files/{job_id}, reads its page count, and rejects
    unsupported or encrypted files. The processing page limit is applied when
    the user starts the job after choosing how many pages to convert.
    """
    original_filename = file.filename or "file.pdf"

    # 1. Path traversal / filename security check
    safe_filename = sanitize_filename(original_filename)
    if ".." in original_filename or "/" in original_filename or "\\" in original_filename:
        # Detected path traversal attempt
        pass  # safe_filename is sanitized to basename

    # 2. Check extension
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: .pdf, .png, .jpg, .jpeg"
        )

    # 3. Create isolated job directory
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job_dir = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id))

    if is_path_traversal(job_dir, DEFAULT_OUTPUT_DIR):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job path")

    os.makedirs(job_dir, exist_ok=True)
    saved_file_path = os.path.join(job_dir, safe_filename)

    # 4. Stream and validate file size
    size_bytes = 0
    effective_max_size = MAX_FILE_SIZE_BYTES
    if max_size_limit is not None and max_size_limit > 0:
        effective_max_size = min(effective_max_size, max_size_limit)

    with open(saved_file_path, "wb") as f_out:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > effective_max_size:
                f_out.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size ({effective_max_size} bytes)"
                )
            f_out.write(chunk)

    # 5. Check page count and encryption for PDF
    total_pages = 1
    if ext == ".pdf":
        try:
            total_pages = await asyncio.to_thread(_inspect_pdf_page_count, saved_file_path)
        except Exception as e:
            err_str = str(e).lower()
            shutil.rmtree(job_dir, ignore_errors=True)
            if "password" in err_str or "encrypted" in err_str or "cannot read encrypted" in err_str:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="PDF มีรหัสผ่าน ไม่รองรับในรุ่นแรก กรุณาปลดรหัสผ่านก่อนอัปโหลด"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot parse PDF file: {e}"
            )

        if max_pages_limit is not None and max_pages_limit > 0 and total_pages > max_pages_limit:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PDF has {total_pages} pages, which exceeds the limit of {max_pages_limit} pages"
            )

    else:
        # Images (PNG / JPG) count as exactly 1 page according to README
        total_pages = 1

    # 6. Save job into DB
    job_status = db.create_job(
        job_id=job_id,
        filename=safe_filename,
        file_path=saved_file_path,
        file_size_bytes=size_bytes,
        total_pages=total_pages,
        enable_ai=True,
    )

    return JobCreateResponse(
        job_id=job_id,
        status=job_status.status,
        filename=safe_filename,
        file_size_bytes=size_bytes,
        total_pages=total_pages,
        created_at=job_status.created_at,
    )


@app.post("/api/jobs/{job_id}/start")
def start_job(job_id: JobId, req: JobStartRequest = JobStartRequest()):
    """
    Enqueues job for processing.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is already running")

    page_start = req.page_start if req.page_start is not None else 1
    page_end = req.page_end if req.page_end is not None else job.total_pages
    selected_count = page_end - page_start + 1
    if page_start < 1 or page_end < page_start or page_end > job.total_pages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ช่วงหน้าที่เลือกไม่อยู่ในเอกสาร")

    # P1 S11: Atomic state transition combining configure and enqueue under JobManager lock
    success = job_manager.configure_and_enqueue_job(
        job_id=job_id,
        page_start=page_start,
        page_end=page_end,
        enable_ai=req.enable_ai,
        include_page_numbers=req.include_page_numbers,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="งานนี้อยู่ในคิว กำลังดำเนินการ หรือไม่สามารถตั้งค่าได้")

    return {
        "message": "Job enqueued successfully",
        "job_id": job_id,
        "status": "queued",
        "processing_pages": selected_count,
        "page_start": page_start,
        "page_end": page_end,
        "batch_size": OCR_BATCH_SIZE,
        "total_batches": max(1, (selected_count + OCR_BATCH_SIZE - 1) // OCR_BATCH_SIZE),
        "include_page_numbers": req.include_page_numbers,
    }


@app.get("/api/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: JobId):
    """
    Retrieves job status with sub-second p95 latency.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: JobId):
    """
    Cancels queued or running job.
    """
    success = job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job cannot be cancelled or already finished")
    # The active worker is terminated to release OneOCR promptly.  Assemble the
    # files here as well, otherwise a cancelled job can expose only page_01.
    from .worker_process import _assemble_job_text_files
    cancelled_job = db.get_job_status(job_id)
    if cancelled_job:
        _assemble_job_text_files(os.path.join(DEFAULT_OUTPUT_DIR, job_id), cancelled_job)
    return {"message": "Cancellation requested", "job_id": job_id, "status": "cancelled"}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: JobId, req: JobRetryRequest = JobRetryRequest()):
    """
    Retries failed steps or failed pages with attempt increment.
    Old attempt results cannot overwrite new attempt.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot retry while job is currently running")

    # If the previous worker process is still terminating, wait up to 2 seconds
    for _ in range(20):
        with job_manager._lock:
            proc = job_manager._active_processes.get(job_id)
            if proc is None or proc.poll() is not None:
                break
        time.sleep(0.1)

    # Increment attempt in DB
    new_attempt = db.increment_attempt(job_id)

    # Enqueue
    success = job_manager.enqueue_job(
        job_id=job_id,
        enable_ai=True if req.retry_mode == "full_text_ai" else job.enable_ai,
        retry_mode=req.retry_mode,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not enqueue job for retry")

    return {
        "message": f"Retry started for attempt {new_attempt}",
        "job_id": job_id,
        "attempt": new_attempt,
        "status": "queued",
    }


@app.get("/api/jobs/{job_id}/download/{file_type}")
def download_output(job_id: JobId, file_type: str, page_start: Optional[int] = Query(None, ge=1), page_end: Optional[int] = Query(None, ge=1)):
    """
    Downloads text results, JSON results, PDF page images, or bundle.zip.
    Includes page breaks and status warnings for partial/failed results.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job_dir = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id))
    headers = {}
    if job.status in (JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED):
        headers["X-Job-Warning"] = f"Warning: Job status is '{job.status.value}'. Some pages may be missing or failed."

    if file_type == "bundle.zip":
        zip_path = os.path.join(job_dir, "bundle.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(job_dir):
                for f in files:
                    if f != "bundle.zip":
                        full_f = os.path.join(root, f)
                        rel_f = os.path.relpath(full_f, job_dir)
                        zf.write(full_f, rel_f)
        return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}_bundle.zip", headers=headers)

    if file_type == "page-images.zip":
        if not job.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page image export is available for PDF files only")
        source_path = db.get_job_raw_path(job_id)
        if not source_path or not os.path.exists(source_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original PDF file is unavailable")

        image_zip_path = os.path.join(job_dir, "page-images.zip")
        try:
            import fitz
            with fitz.open(source_path) as pdf:
                if page_start is not None or page_end is not None:
                    start = page_start if page_start is not None else 1
                    end = page_end if page_end is not None else len(pdf)
                    if start > end or end > len(pdf):
                        raise HTTPException(status_code=400, detail="Invalid page range")
                    page_numbers = range(start, end + 1)
                else:
                    page_numbers = [page.page_num for page in job.pages]
                with zipfile.ZipFile(image_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for page_num in page_numbers:
                        pix = pdf[page_num - 1].get_pixmap(dpi=200, alpha=False)
                        zf.writestr(f"page_{page_num:04d}.png", pix.tobytes("png"))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to convert PDF pages to images: {e}")
        return FileResponse(image_zip_path, media_type="application/zip", filename=f"{job_id}_page-images.zip", headers=headers)

    valid_files = {
        "raw.txt": ("text/plain; charset=utf-8", "raw.txt"),
        "corrected.txt": ("text/plain; charset=utf-8", "corrected.txt"),
        "final.txt": ("text/plain; charset=utf-8", "final.txt"),
        "ocr.json": ("application/json; charset=utf-8", "ocr.json"),
        "changes.json": ("application/json; charset=utf-8", "changes.json"),
    }

    if file_type not in valid_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_type '{file_type}'. Supported: {list(valid_files.keys())} or bundle.zip"
        )

    media_type, fname = valid_files[file_type]
    file_path = os.path.join(job_dir, fname)

    # If top-level file doesn't exist yet, look into page 01 or create from pages
    if not os.path.exists(file_path):
        p1_path = os.path.join(job_dir, "page_01", fname)
        if os.path.exists(p1_path):
            file_path = p1_path
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requested output file '{file_type}' has not been generated yet"
            )

    return FileResponse(file_path, media_type=media_type, filename=f"{job_id}_{fname}", headers=headers)


@app.put("/api/jobs/{job_id}/pages/{page_id}/edit", response_model=PageEditResponse)
def edit_page_text(job_id: JobId, page_id: int, req: PageEditRequest):
    """
    Saves user manual edit to final.txt for a page with strict revision checking.
    Raises 409 Conflict if source_revision does not match current database revision.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        res = db.save_page_edit(
            job_id=job_id,
            page_id=page_id,
            source_revision=req.source_revision,
            edited_text=req.edited_text,
            output_dir=DEFAULT_OUTPUT_DIR,
            check_conflict=req.check_conflict,
        )
        return PageEditResponse(
            page_id=page_id,
            new_revision=res["new_revision"],
            status="saved",
            message=res["message"],
        )
    except (RevisionConflictError, DatabaseLockTimeoutError):
        raise
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/jobs/{job_id}/pages/{page_id}/corrections/{change_id}/accept")
def accept_correction(job_id: JobId, page_id: int, change_id: str):
    """
    Accepts an AI proposal, applying replacement to final.txt and incrementing revision.
    """
    try:
        res = db.apply_proposal_action(
            job_id=job_id,
            page_id=page_id,
            change_id=change_id,
            action="accept",
            output_dir=DEFAULT_OUTPUT_DIR,
        )
        return res
    except (RevisionConflictError, DatabaseLockTimeoutError):
        raise
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/jobs/{job_id}/pages/{page_id}/corrections/{change_id}/revert")
def revert_correction(job_id: JobId, page_id: int, change_id: str):
    """
    Reverts an AI proposal back to raw text and increments revision.
    """
    try:
        res = db.apply_proposal_action(
            job_id=job_id,
            page_id=page_id,
            change_id=change_id,
            action="revert",
            output_dir=DEFAULT_OUTPUT_DIR,
        )
        return res
    except (RevisionConflictError, DatabaseLockTimeoutError):
        raise
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/jobs/{job_id}/pages/{page_id}/corrections/accept-all")
def accept_all_corrections(
    job_id: JobId,
    page_id: int,
    source_revision: Optional[int] = Query(None, description="Optional revision expected for conflict check"),
):
    """
    Accepts all AI proposals for a page in batch (Bug 5).
    """
    try:
        res = db.apply_all_proposals(
            job_id=job_id,
            page_id=page_id,
            action="accept",
            output_dir=DEFAULT_OUTPUT_DIR,
            source_revision=source_revision,
        )
        return res
    except (RevisionConflictError, DatabaseLockTimeoutError):
        raise
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/jobs/{job_id}/pages/{page_id}/corrections/revert-all")
def revert_all_corrections(
    job_id: JobId,
    page_id: int,
    source_revision: Optional[int] = Query(None, description="Optional revision expected for conflict check"),
):
    """
    Reverts all AI proposals for a page in batch (Bug 5).
    """
    try:
        res = db.apply_all_proposals(
            job_id=job_id,
            page_id=page_id,
            action="revert",
            output_dir=DEFAULT_OUTPUT_DIR,
            source_revision=source_revision,
        )
        return res
    except (RevisionConflictError, DatabaseLockTimeoutError):
        raise
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/jobs/{job_id}/pages/{page_id}/image")
def get_page_image(job_id: JobId, page_id: int):
    """
    Serves the reference image of a page for the dual-pane viewer.
    Renders from original document if not already cached.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job_dir = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id))
    page_dir = os.path.join(job_dir, f"page_{page_id:02d}")
    img_path = os.path.join(page_dir, "image.png")

    if os.path.exists(img_path):
        return FileResponse(img_path, media_type="image/png")

    # Render or extract from source document
    src_file = db.get_job_raw_path(job_id)
    if not src_file or not os.path.exists(src_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")

    os.makedirs(page_dir, exist_ok=True)
    ext = os.path.splitext(src_file)[1].lower()

    if ext == ".pdf":
        import fitz
        try:
            doc = fitz.open(src_file)
            p_idx = max(0, min(page_id - 1, len(doc) - 1))
            page = doc[p_idx]
            pix = page.get_pixmap(dpi=150)
            pix.save(img_path)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to render PDF page image: {e}")
    else:
        from PIL import Image
        try:
            with Image.open(src_file) as im:
                im.convert("RGB").save(img_path, "PNG")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to convert image: {e}")

    return FileResponse(img_path, media_type="image/png")


@app.get("/api/jobs/{job_id}/pages/{page_id}/data")
def get_page_data(job_id: JobId, page_id: int):
    """
    Returns full structured data for a page: raw text, corrected text, final text,
    revision, bounding boxes, character mappings, and AI change proposals.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    page_info = None
    for p in job.pages:
        if p.page_id == page_id or p.page_num == page_id:
            page_info = p
            break

    job_dir = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id))
    page_dir = os.path.join(job_dir, f"page_{page_id:02d}")

    raw_path = os.path.join(page_dir, "raw.txt")
    corr_path = os.path.join(page_dir, "corrected.txt")
    final_path = os.path.join(page_dir, "final.txt")
    ocr_json_path = os.path.join(page_dir, "ocr.json")
    changes_json_path = os.path.join(page_dir, "changes.json")

    raw_text = ""
    if os.path.exists(raw_path):
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

    corr_text = raw_text
    if os.path.exists(corr_path):
        with open(corr_path, "r", encoding="utf-8") as f:
            corr_text = f.read()

    final_text = raw_text
    if os.path.exists(final_path):
        with open(final_path, "r", encoding="utf-8") as f:
            final_text = f.read()

    # Load ocr.json if present
    blocks = []
    char_mapping = []
    reference_image = {"width": 1000, "height": 1400}
    transform = {"angle": 0.0, "scale_x": 1.0, "scale_y": 1.0, "translate_x": 0.0, "translate_y": 0.0}

    target_ocr_json = ocr_json_path if os.path.exists(ocr_json_path) else os.path.join(job_dir, "ocr.json")
    if os.path.exists(target_ocr_json):
        try:
            with open(target_ocr_json, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                for p_rec in ocr_data.get("pages", []):
                    if p_rec.get("page_id") == page_id or p_rec.get("page_num") == page_id:
                        blocks = p_rec.get("blocks", [])
                        char_mapping = p_rec.get("char_mapping", [])
                        reference_image = p_rec.get("reference_image", reference_image)
                        transform = p_rec.get("transform", transform)
                        break
        except Exception:
            pass

    changes = []
    diff_summary = {}
    if os.path.exists(changes_json_path):
        try:
            with open(changes_json_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                changes = cdata.get("corrections", [])
                diff_summary = cdata.get("diff_summary", {})
        except Exception:
            pass

    current_rev = page_info.revision if page_info else 1
    has_edit = page_info.has_manual_edit if page_info else False

    return {
        "job_id": job_id,
        "page_id": page_id,
        "page_num": page_id,
        "status": page_info.status.value if page_info else "unknown",
        "ocr_status": page_info.ocr_status.value if page_info else "unknown",
        "ai_status": page_info.ai_status.value if page_info else "unknown",
        "revision": current_rev,
        "has_manual_edit": has_edit,
        "review_status": job.review_status.value,
        "raw_text": raw_text,
        "corrected_text": corr_text,
        "final_text": final_text,
        "reference_image": {
            "width": reference_image.get("width", 1000),
            "height": reference_image.get("height", 1400),
            "url": f"/api/jobs/{job_id}/pages/{page_id}/image",
        },
        "transform": transform,
        "blocks": blocks,
        "char_mapping": char_mapping,
        "changes": changes,
        "diff_summary": diff_summary,
    }


@app.post("/api/jobs/{job_id}/review")
def update_review_status(job_id: JobId, new_status: ReviewStatus = Query(...)):
    """
    Updates review status: unreviewed -> in_review -> reviewed.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    db.update_job_status(job_id, job.status, review_status=new_status)
    return {"job_id": job_id, "review_status": new_status.value}


@app.get("/api/jobs")
def list_jobs(limit: int = 50):
    return db.list_jobs(limit=limit)


# Static files for Phase 5 Web UI
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, encoding="utf-8") as source:
            markup = source.read()
        for name in ("text", "html", "epub", "structured"):
            with open(os.path.join(STATIC_DIR, f"{name}.html"), encoding="utf-8") as partial:
                markup = markup.replace(f"<!-- include:{name}.html -->", partial.read())
        return HTMLResponse(markup)
    return PlainTextResponse("Local Thai OCR API is running. UI static file not created yet.")


@app.get("/config.html", response_class=FileResponse)
def serve_config():
    """Serves the Local LLM configuration page from the static UI bundle."""
    config_file = os.path.join(STATIC_DIR, "config.html")
    if os.path.exists(config_file):
        return FileResponse(config_file)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration page not found")


# ------------------------------------------------------------------------------
# Phase 6: Admin Retention & Cleanup Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/admin/cleanup")
def trigger_cleanup(max_age_seconds: Optional[float] = Query(None, description="Max age in seconds for expired jobs")):
    """
    Triggers data retention cleanup cycle, removing expired finalized jobs and their files.
    Active running or queued jobs are strictly protected and never deleted.
    """
    from src.cleanup_service import cleanup_expired_jobs
    res = cleanup_expired_jobs(
        db=db,
        output_base_dir=DEFAULT_OUTPUT_DIR,
        retention_seconds=max_age_seconds,
        job_manager=job_manager,
    )
    return res


@app.delete("/api/admin/jobs")
def delete_all_jobs_endpoint():
    """Explicit confirmed bulk deletion, including queued and running jobs."""
    try:
        return job_manager.delete_all_jobs()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@app.delete("/api/jobs/{job_id}")
def delete_job_endpoint(job_id: JobId, force: bool = Query(False)):
    """
    Explicitly deletes a job and its artifacts from filesystem and database.
    If job is currently running or queued and force=False, returns HTTP 400.
    """
    from src.cleanup_service import delete_single_job
    if html_ai_tasks.is_active(job_id):
        raise HTTPException(status_code=409, detail="กรุณายกเลิกการสร้าง HTML ด้วย AI และรอให้หยุดก่อนลบงาน")
    try:
        res = delete_single_job(
            job_id=job_id,
            db=db,
            output_base_dir=DEFAULT_OUTPUT_DIR,
            job_manager=job_manager,
            force=force,
        )
        if not res.get("deleted") and res.get("details") == "Job not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return res
    except ValueError as e:
        raise HTTPException(status_code=409 if str(e).startswith("Conflict:") else 400, detail=str(e))


# ------------------------------------------------------------------------------
# Phase 7: Structured HTML Export Endpoints
# ------------------------------------------------------------------------------

class HtmlExportRequest(BaseModel):
    mode: str = "basic"


class SaveFinalHtmlRequest(BaseModel):
    html_content: str
    base_revision: Optional[str] = None
    overwrite: bool = False


class EpubPreviewRequest(BaseModel):
    source_variant: str = "auto"
    metadata: Optional[Dict[str, Any]] = None
    chapter_split: str = "heading"
    cover: Optional[Dict[str, Any]] = None
    toc_revision: Optional[str] = None


class EpubPackageRequest(BaseModel):
    base_preview_revision: str


class TocSaveRequest(BaseModel):
    entries: List[Dict[str, Any]]
    base_source_revision: str
    base_toc_revision: str
    base_preview_revision: Optional[str] = None
    source_variant: str = "auto"
    chapter_split: str = "heading"


class TocRegenerateRequest(BaseModel):
    confirm: bool = False
    base_source_revision: str
    base_toc_revision: str
    base_preview_revision: Optional[str] = None
    source_variant: str = "auto"
    chapter_split: str = "heading"


# ------------------------------------------------------------------------------
# Phase 8.1: Structured OCR exports (reuses saved OCR; never starts OCR/AI)
# ------------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/export/structured")
def export_structured_endpoint(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.structured_layout import generate_structured_exports
    try:
        meta = generate_structured_exports(job_id, files_dir=DEFAULT_OUTPUT_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"status": "ready", "meta": meta}


@app.get("/api/jobs/{job_id}/export/structured/status")
def export_structured_status_endpoint(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.structured_layout import get_structured_status
    return get_structured_status(job_id, files_dir=DEFAULT_OUTPUT_DIR)


@app.get("/api/jobs/{job_id}/export/structured/{variant}")
def download_structured_endpoint(
    job_id: JobId,
    variant: str = Path(pattern=r"^(text|html|layout)$"),
):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    names = {"text": ("structured.txt", "text/plain; charset=utf-8"),
             "html": ("structured.html", "text/html; charset=utf-8"),
             "layout": ("layout.json", "application/json; charset=utf-8")}
    filename, media_type = names[variant]
    file_path = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id, "export", "structured", filename))
    if is_path_traversal(file_path, DEFAULT_OUTPUT_DIR) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Structured {variant} export not found")
    from urllib.parse import quote
    download_name = f"{job.filename}_{filename}"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(download_name)}",
        "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    return FileResponse(file_path, media_type=media_type, headers=headers)


@app.post("/api/jobs/{job_id}/export/html/ai/start", status_code=202)
def start_html_ai_task(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        return html_ai_tasks.start(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/jobs/{job_id}/export/html/ai/progress")
def get_html_ai_progress(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(html_ai_tasks.status(job_id), headers={"Cache-Control": "no-store"})


@app.post("/api/jobs/{job_id}/export/html/ai/cancel")
def cancel_html_ai_task(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return html_ai_tasks.cancel(job_id)


@app.post("/api/jobs/{job_id}/export/html")
def export_html_endpoint(job_id: JobId, req: HtmlExportRequest = HtmlExportRequest()):
    """
    Generates structured HTML (basic.html or ai.html).
    basic: 100% deterministic, offline without AI.
    ai: Uses Local LLM to suggest semantic tags if online; otherwise preserves basic.html.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    mode = req.mode.lower().strip()
    if mode not in ("basic", "ai"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allowed export modes: 'basic', 'ai'")
    if html_ai_tasks.is_active(job_id):
        raise HTTPException(status_code=409, detail="กำลังสร้าง HTML ด้วย AI กรุณารอหรือยกเลิกงานเดิมก่อนสร้างใหม่")

    if mode == "ai":
        from src.llm_client import LocalLLMClient
        from src.html_exporter import generate_ai_html, generate_basic_html, _update_export_meta

        # Checklist 407: Enforce at most 1 concurrent Local LLM job across OCR+AI and AI export
        if job_manager.is_ai_in_use() and not job_manager.ai_lock.locked():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local AI กำลังประมวลผลงาน OCR+AI อื่นอยู่ ไม่สามารถส่งออก AI ซ้อนกันได้ กรุณารอให้งานปัจจุบันเสร็จสิ้น",
            )

        acquired = job_manager.ai_lock.acquire(timeout=5.0)
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local AI กำลังถูกใช้งานโดยงานอื่นอยู่ (จำกัด 1 งานพร้อมกัน)",
            )
        try:
            client = LocalLLMClient()
            health = client.check_health()
            if health.get("status") not in ("connected", "healthy"):
                # AI is offline: generate basic.html as fallback and record locked_ai_offline status
                basic_html, meta = generate_basic_html(job_id, files_dir=DEFAULT_OUTPUT_DIR)
                job_dir = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id))
                from datetime import datetime, timezone
                ai_meta = {
                    "mode": "ai",
                    "model": getattr(client, "model", "google/gemma-3-1b"),
                    "prompt_version": "v1.0",
                    "temperature": 0.0,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "chunk_count": 0,
                    "source_revision": meta.get("source_revision", ""),
                    "validator_status": "locked_ai_offline",
                    "message": health.get("error") or "Local AI is offline. Basic HTML preserved.",
                }
                _update_export_meta(job_dir, "ai", ai_meta)
                return {
                    "status": "locked_ai_offline",
                    "mode": "ai",
                    "detail": ai_meta["message"],
                    "ai_applied": False,
                    "meta": ai_meta,
                }
            content, meta = generate_ai_html(job_id, files_dir=DEFAULT_OUTPUT_DIR, llm_client=client)
            return {"status": meta.get("validator_status", "ready"), "mode": "ai",
                    "ai_applied": meta.get("validator_status") == "passed", "meta": meta}
        finally:
            job_manager.ai_lock.release()

    else:
        from src.html_exporter import generate_basic_html
        content, meta = generate_basic_html(job_id, files_dir=DEFAULT_OUTPUT_DIR)
        return {"status": "ready", "mode": "basic", "meta": meta}


@app.get("/api/jobs/{job_id}/export/html/status")
def export_html_status_endpoint(job_id: JobId):
    """
    Returns HTML export status, source revision, and stale indicator.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from src.html_exporter import get_export_status
    return get_export_status(job_id, files_dir=DEFAULT_OUTPUT_DIR)


@app.get("/api/jobs/{job_id}/export/html/{variant}")
def download_html_endpoint(
    job_id: JobId,
    variant: str = Path(pattern=r"^(basic|ai|final)$"),
):
    """
    Downloads exported HTML file with RFC 5987 UTF-8 encoded filename and nosniff protection.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    file_path = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id, "export", f"{variant}.html"))
    if is_path_traversal(file_path, DEFAULT_OUTPUT_DIR) or not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Export {variant}.html not found")

    from urllib.parse import quote
    filename = f"{job.filename}_{variant}.html"
    encoded_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename=\"{variant}.html\"; filename*=UTF-8''{encoded_filename}",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(file_path, media_type="text/html; charset=utf-8", headers=headers)


@app.get("/api/jobs/{job_id}/export/html/{variant}/preview")
def preview_html_endpoint(
    job_id: JobId,
    variant: str = Path(pattern=r"^(basic|ai|final)$"),
):
    """
    Returns HTML for sandboxed preview with Content-Security-Policy sandbox enforcement.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    file_path = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id, "export", f"{variant}.html"))
    if is_path_traversal(file_path, DEFAULT_OUTPUT_DIR) or not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Export {variant}.html not found")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    headers = {
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=content, media_type="text/html; charset=utf-8", headers=headers)


@app.put("/api/jobs/{job_id}/export/html/final")
def save_final_html_endpoint(job_id: JobId, req: SaveFinalHtmlRequest):
    """
    Saves user-edited final.html with sanitization and revision conflict checking.
    Returns HTTP 409 if source_revision changed, unless overwrite=True.
    """
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    from src.html_exporter import save_final_html
    try:
        meta = save_final_html(
            job_id=job_id,
            final_html_content=req.html_content,
            base_revision=req.base_revision,
            overwrite=req.overwrite,
            files_dir=DEFAULT_OUTPUT_DIR,
        )
        return {"status": "saved", "meta": meta}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# ------------------------------------------------------------------------------
# Phase 8: EPUB Export & XHTML Quick Preview Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/export/epub/preview")
def prepare_epub_preview_endpoint(job_id: JobId, req: EpubPreviewRequest):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from src.epub_exporter import prepare_epub_preview
    try:
        meta = prepare_epub_preview(
            job_id=job_id,
            source_variant=req.source_variant,
            metadata=req.metadata,
            chapter_split=req.chapter_split,
            cover=req.cover,
            toc_revision=req.toc_revision,
            files_dir=DEFAULT_OUTPUT_DIR,
        )
        return {"status": "preview_ready", "meta": meta}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Conflict:") else 400, detail=str(exc))


@app.get("/api/jobs/{job_id}/export/epub/preview")
def get_epub_preview_endpoint(job_id: JobId):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from src.epub_exporter import get_epub_preview
    try:
        content = get_epub_preview(job_id, files_dir=DEFAULT_OUTPUT_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return Response(
        content=content,
        media_type="application/xhtml+xml; charset=utf-8",
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src http://127.0.0.1:* http://localhost:* http://[::1]:*; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/jobs/{job_id}/export/epub/toc")
def get_epub_toc_endpoint(
    job_id: JobId,
    source_variant: str = Query("auto", pattern=r"^(auto|basic|ai|final|structured)$"),
    chapter_split: str = Query("heading", pattern=r"^(heading|page)$"),
):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.toc_editor import editor_state
    try:
        return editor_state(job_id, DEFAULT_OUTPUT_DIR, source_variant, chapter_split)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Conflict:") else 422, detail=str(exc))


@app.put("/api/jobs/{job_id}/export/epub/toc")
def save_epub_toc_endpoint(job_id: JobId, req: TocSaveRequest):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.toc_editor import save_editor_toc
    try:
        model = save_editor_toc(job_id, req.entries, req.base_source_revision, req.base_toc_revision,
                                req.base_preview_revision, DEFAULT_OUTPUT_DIR,
                                req.source_variant, req.chapter_split)
        return {"status": "saved", "toc": model}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Conflict:") else 422, detail=str(exc))


@app.post("/api/jobs/{job_id}/export/epub/toc/regenerate")
def regenerate_epub_toc_endpoint(job_id: JobId, req: TocRegenerateRequest):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.toc_editor import regenerate_toc
    try:
        model = regenerate_toc(job_id, req.confirm, req.base_source_revision, req.base_toc_revision,
                               req.base_preview_revision, DEFAULT_OUTPUT_DIR,
                               req.source_variant, req.chapter_split)
        return {"status": "saved", "toc": model}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Conflict:") else 422, detail=str(exc))


@app.get("/api/jobs/{job_id}/export/epub/cover")
def get_epub_cover_endpoint(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    from src.epub_exporter import _safe_job_dir, _read_json
    import base64
    path = os.path.join(_safe_job_dir(DEFAULT_OUTPUT_DIR, job_id), 'export', 'epub', 'preview_payload.json')
    cover = _read_json(path).get('cover')
    if not cover:
        raise HTTPException(status_code=404, detail="No cover")
    return Response(base64.b64decode(cover['data_base64']), media_type='image/png',
                    headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@app.get("/api/jobs/{job_id}/export/epub/cover/pdf-pages")
def get_epub_cover_pdf_pages_endpoint(job_id: JobId):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    source_path = db.get_job_raw_path(job_id)
    if not source_path or not os.path.isfile(source_path):
        raise HTTPException(status_code=404, detail="Source file not found")
    if os.path.splitext(source_path)[1].lower() != '.pdf':
        raise HTTPException(status_code=422, detail="EPUB cover page source must be a PDF")
    try:
        return {"page_count": _inspect_pdf_page_count(source_path)}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot read PDF pages: {exc}")


@app.get("/api/jobs/{job_id}/export/epub/cover/pdf-page/{page_num}")
def get_epub_cover_pdf_page_endpoint(job_id: JobId, page_num: int):
    if not db.get_job_status(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    source_path = db.get_job_raw_path(job_id)
    if not source_path or not os.path.isfile(source_path):
        raise HTTPException(status_code=404, detail="Source file not found")
    if os.path.splitext(source_path)[1].lower() != '.pdf':
        raise HTTPException(status_code=422, detail="EPUB cover page source must be a PDF")
    import pymupdf
    try:
        with pymupdf.open(source_path) as document:
            if page_num < 1 or page_num > len(document):
                raise HTTPException(status_code=422, detail=f"PDF page must be between 1 and {len(document)}")
            image_bytes = document[page_num - 1].get_pixmap(dpi=150, alpha=False).tobytes('png')
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot render PDF cover page: {exc}")
    return Response(image_bytes, media_type='image/png',
                    headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@app.post("/api/jobs/{job_id}/export/epub")
def build_epub_endpoint(job_id: JobId, req: EpubPackageRequest):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from src.epub_exporter import build_epub
    try:
        meta = build_epub(
            job_id=job_id,
            base_preview_revision=req.base_preview_revision,
            files_dir=DEFAULT_OUTPUT_DIR,
        )
        return {"status": "ready", "meta": meta}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        code = status.HTTP_409_CONFLICT if message.startswith("Conflict:") else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=message)


@app.get("/api/jobs/{job_id}/export/epub/status")
def get_epub_status_endpoint(job_id: JobId):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from src.epub_exporter import get_epub_status
    return get_epub_status(job_id, files_dir=DEFAULT_OUTPUT_DIR)


@app.get("/api/jobs/{job_id}/export/epub/download")
def download_epub_endpoint(job_id: JobId):
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    file_path = os.path.abspath(os.path.join(DEFAULT_OUTPUT_DIR, job_id, "export", "epub", "book.epub"))
    if is_path_traversal(file_path, DEFAULT_OUTPUT_DIR) or not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPUB not generated")
    from urllib.parse import quote
    base_name = os.path.splitext(job.filename or "document")[0]
    encoded_filename = quote(f"{base_name}.epub")
    from src.job_artifact_guard import artifact_access
    from src.epub_exporter import get_epub_status
    try:
        with artifact_access(job_id, DEFAULT_OUTPUT_DIR):
            if not get_epub_status(job_id, files_dir=DEFAULT_OUTPUT_DIR).get('epub_ready'):
                raise HTTPException(status_code=409, detail='EPUB is stale or not ready; regenerate preview and package')
            with open(file_path, 'rb') as stream:
                content = stream.read()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='EPUB not generated')
    return Response(content, media_type="application/epub+zip", headers={
        "Content-Disposition": f"attachment; filename=\"book.epub\"; filename*=UTF-8''{encoded_filename}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})



if __name__ == "__main__":
    import uvicorn
    print(f"Starting Local Thai OCR API on {HOST}:{PORT} (Localhost only: {LOCALHOST_ONLY})")
    uvicorn.run("src.server:app", host=HOST, port=PORT, reload=False)
