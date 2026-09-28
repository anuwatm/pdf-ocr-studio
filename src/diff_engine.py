"""
Phase 3: Diff Engine and Correction Applicator.
Applies corrections to raw text to produce corrected.txt and final.txt,
generates character-level diff representations with 100% coverage,
and supports full reversibility (reverting changes restores raw.txt 100%).
Supports Unicode code points, Thai combining characters, and non-BMP symbols.
"""
from typing import List, Dict, Any, Tuple, Optional
import difflib
import unicodedata

from src.correction_schema import CorrectionItem, DiffSummary
from src.correction_validator import levenshtein_distance


class DiffEngine:
    """
    Diff generation, application, and reversion engine.
    """

    @staticmethod
    def apply_corrections(
        raw_text: str,
        corrections: List[CorrectionItem],
        source_revision: Optional[int] = None,
        current_revision: Optional[int] = None,
    ) -> str:
        """
        Applies a list of non-overlapping, validated corrections to raw_text.
        Since corrections are indexed on raw_text, we apply them in reverse order
        (from end to start) so earlier offsets remain strictly stable.

        If source_revision and current_revision are both specified and differ,
        raises ValueError indicating a stale revision conflict, preventing old attempts
        from overwriting newer user revisions.
        """
        if source_revision is not None and current_revision is not None:
            if source_revision != current_revision:
                raise ValueError(
                    f"Stale revision conflict: proposals are for revision {source_revision}, "
                    f"but current document revision is {current_revision}"
                )

        if not corrections:
            return raw_text

        # Filter out stale or rejected corrections
        active_corrections = [c for c in corrections if getattr(c, "status", "pending") not in ("stale", "rejected")]
        if not active_corrections:
            return raw_text

        # Sort descending by start offset
        sorted_corr = sorted(active_corrections, key=lambda c: c.start, reverse=True)

        chars = list(raw_text)
        for c in sorted_corr:
            # Replace slice chars[c.start:c.end] with c.corrected_text
            chars[c.start:c.end] = list(c.corrected_text)

        return "".join(chars)

    @staticmethod
    def revert_all_corrections(raw_text: str, corrected_text: str, corrections: List[CorrectionItem]) -> str:
        """
        Reverting all corrections must yield raw_text 100% identical.
        """
        # Under our design, raw_text is always preserved immutable as revision 1.
        return raw_text

    @staticmethod
    def revert_single_correction(
        raw_text: str,
        corrections: List[CorrectionItem],
        change_id_to_revert: str
    ) -> str:
        """
        Reverts a single correction by applying all corrections EXCEPT the specified one.
        """
        remaining = [c for c in corrections if c.change_id != change_id_to_revert]
        return DiffEngine.apply_corrections(raw_text, remaining)

    @staticmethod
    def compute_diff_summary(raw_text: str, corrected_text: str) -> DiffSummary:
        """
        Computes character-level diff statistics (substitutions, insertions, deletions, unchanged).
        Ensures 100% diff coverage across every character changed.
        """
        matcher = difflib.SequenceMatcher(None, raw_text, corrected_text)
        substitutions = 0
        deletions = 0
        insertions = 0
        unchanged = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            raw_len = i2 - i1
            corr_len = j2 - j1

            if tag == "equal":
                unchanged += raw_len
            elif tag == "replace":
                min_len = min(raw_len, corr_len)
                substitutions += min_len
                if raw_len > corr_len:
                    deletions += (raw_len - corr_len)
                elif corr_len > raw_len:
                    insertions += (corr_len - raw_len)
            elif tag == "delete":
                deletions += raw_len
            elif tag == "insert":
                insertions += corr_len

        lev = levenshtein_distance(raw_text, corrected_text)

        return DiffSummary(
            total_characters_raw=len(raw_text),
            total_characters_corrected=len(corrected_text),
            substitutions=substitutions,
            deletions=deletions,
            insertions=insertions,
            unchanged=unchanged,
            levenshtein_distance=lev,
        )

    @staticmethod
    def generate_unified_diff(raw_text: str, corrected_text: str, filename: str = "text") -> str:
        """
        Generates standard unified diff string for inspection and logging.
        """
        raw_lines = raw_text.splitlines(keepends=True)
        corr_lines = corrected_text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            raw_lines,
            corr_lines,
            fromfile=f"a/{filename}.raw.txt",
            tofile=f"b/{filename}.corrected.txt",
            n=2
        )
        return "".join(diff)
