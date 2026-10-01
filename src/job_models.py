"""
Phase 4: Job & API Schema Definitions.
Defines Pydantic models and Enums for Job Queue, Worker, and FastAPI REST endpoints.
Strictly follows README and Checklist specifications.
"""
from typing import List, Optional, Dict, Any, Literal, get_args
from enum import Enum
from pydantic import BaseModel, Field

OCR_BATCH_SIZE = 200
RetryMode = Literal["failed_only", "ai_only", "full", "full_text_ai"]
RETRY_MODES = get_args(RetryMode)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLANK = "blank"
    SKIPPED = "skipped"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"


class PageProgress(BaseModel):
    page_id: int
    page_num: int
    status: PageStatus = PageStatus.QUEUED
    ocr_status: StageStatus = StageStatus.PENDING
    ai_status: StageStatus = StageStatus.PENDING
    attempt_number: int = 1
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    raw_text_length: int = 0
    corrections_count: int = 0
    revision: int = 1
    has_manual_edit: bool = False


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    filename: str
    file_size_bytes: int
    total_pages: int
    created_at: str


class JobStartRequest(BaseModel):
    enable_ai: bool = True
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)
    include_page_numbers: bool = True


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    filename: str
    file_size_bytes: int
    total_pages: int
    batch_size: int = OCR_BATCH_SIZE
    total_batches: int = 1
    current_batch: int = 1
    completed_pages: int = 0
    failed_pages: int = 0
    cancelled_pages: int = 0
    current_attempt: int = 1
    enable_ai: bool = True
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    pages: List[PageProgress] = Field(default_factory=list)


class JobRetryRequest(BaseModel):
    retry_mode: RetryMode = "failed_only"


class PageEditRequest(BaseModel):
    source_revision: int
    edited_text: str
    check_conflict: bool = False


class PageEditResponse(BaseModel):
    page_id: int
    new_revision: int
    status: str
    message: str


class LocalLLMConfigRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=300)
    model: str = Field(min_length=1, max_length=200)
    timeout: float = Field(ge=1, le=300)
    api_key: Optional[str] = Field(default=None, max_length=500)
