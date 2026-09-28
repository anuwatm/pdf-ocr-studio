"""
Phase 3: AI Text Correction Schemas and Data Models.
Defines data structures for AI proposals, UI highlights, diff representations,
and change tracking documents per README and Checklist specifications.
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class HighlightSpan(BaseModel):
    """
    UI Highlight Span for frontend rendering.
    Expands boundary to complete Grapheme Cluster (base consonant + vowels + tone marks)
    without altering the actual code-point replacement span [start, end).
    """
    display_start: int = Field(..., description="Expanded start offset for visual highlight")
    display_end: int = Field(..., description="Expanded end offset for visual highlight")
    base_character: Optional[str] = Field(None, description="Base consonant if vowel/tone replacement")


class CorrectionItem(BaseModel):
    """
    Individual text correction proposal by AI.
    Bound strictly to a block_id, line_index, and Unicode code-point offset range [start, end).
    """
    change_id: str = Field(..., description="Unique identifier for this correction (e.g. chg_1)")
    block_id: str = Field(..., description="Origin block ID in ocr.json")
    line_index: Optional[int] = Field(None, description="Line index within the block")
    start: int = Field(..., description="Start offset in Unicode code points [start, end)")
    end: int = Field(..., description="End offset in Unicode code points [start, end)")
    original_text: str = Field(..., description="Exact substring in raw text at [start, end)")
    corrected_text: str = Field(..., description="Proposed replacement text")
    category: Literal["spelling", "vowel_tone", "whitespace", "number", "named_entity", "other"] = Field(
        "spelling", description="Category of the correction"
    )
    reason: str = Field("", description="Explanation for the change")
    status: Literal["pending", "accepted", "rejected", "stale"] = Field(
        "pending", description="Review status of the proposal"
    )
    is_named_entity_or_number: bool = Field(
        False, description="Flagged for mandatory manual review if number or proper name"
    )
    ui_highlight: Optional[HighlightSpan] = Field(
        None, description="Expanded visual highlight span for UI"
    )


class DiffSummary(BaseModel):
    """
    Summary of character-level diff between raw and corrected text.
    """
    total_characters_raw: int = 0
    total_characters_corrected: int = 0
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    unchanged: int = 0
    levenshtein_distance: int = 0


class ChangesDocument(BaseModel):
    """
    Full changes.json document for a page or document.
    Maintains revision provenance, audit trail, and status.
    """
    schema_version: str = "3.0.0"
    job_id: str = Field(..., description="Job identifier")
    page_id: int = Field(..., description="Page number/ID")
    source_revision: int = Field(1, description="Origin revision number (1 = raw.txt)")
    current_revision: Optional[int] = Field(None, description="Current revision number of target document")
    status: Literal["completed", "partial", "timeout", "connection_error", "malformed_json", "failed", "stale"] = Field(
        "completed", description="Execution status of AI correction"
    )
    model: str = Field("google/gemma-3-1b", description="Model name used")
    error_message: Optional[str] = Field(None, description="Error detail if status is not completed")
    total_corrections: int = 0
    accepted_corrections: int = 0
    rejected_corrections: int = 0
    pending_corrections: int = 0
    stale_corrections: int = 0
    corrections: List[CorrectionItem] = Field(default_factory=list)
    rejected_proposals: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trail of rejected or stale candidate proposals")
    diff_summary: DiffSummary = Field(default_factory=DiffSummary)
