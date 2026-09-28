"""
Phase 3: Correction Validator & Schema Integrity Checker.
Enforces all checklist constraints:
1. Exact substring matching (raw_text[start:end] == original_text)
2. Non-overlapping spans
3. Block ID provenance verification
4. Edit distance & length filtering (reject hallucinated paragraphs)
5. Adversarial prompt injection defense
6. Flagging numbers and named entities for human inspection
7. UI highlight grapheme cluster calculation without altering replacement offsets
"""
from typing import List, Dict, Any, Tuple, Optional, Set
import re
import unicodedata

from src.correction_schema import CorrectionItem, HighlightSpan

# Regex for detecting prompt injection / adversarial patterns
INJECTION_KEYWORDS = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"คำสั่งลับ", re.IGNORECASE),
    re.compile(r"ลบข้อความทั้งหมด", re.IGNORECASE),
    re.compile(r"ให้แต่งนิทาน", re.IGNORECASE),
    re.compile(r"สรุปเนื้อหาเป็น", re.IGNORECASE),
]

DIGIT_PATTERN = re.compile(r"[\d\u0e50-\u0e59]")
THAI_VOWEL_TONE_ONLY = re.compile(r"^[\u0e31\u0e34-\u0e39\u0e48-\u0e4c]+$")
THAI_CONSONANTS = set("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein distance on Unicode code points."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (c1 != c2)
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


class CorrectionValidator:
    """
    Validates and filters proposed corrections against raw text and structural metadata.
    """

    @staticmethod
    def calculate_ui_highlight(text: str, start: int, end: int) -> HighlightSpan:
        """
        Calculates expanded display span for UI rendering.
        If replacement targets only combining vowels or tone marks, expands
        backwards to the base consonant so that the full glyph is visible in the browser.
        """
        display_start = start
        display_end = end
        base_char = None

        target = text[start:end]
        if THAI_VOWEL_TONE_ONLY.match(target):
            # Scan backwards to find the base consonant
            k = start - 1
            while k >= 0:
                char = text[k]
                if char in THAI_CONSONANTS:
                    display_start = k
                    base_char = char
                    break
                elif char in "\n\r\t ":
                    break
                k -= 1

        return HighlightSpan(
            display_start=display_start,
            display_end=display_end,
            base_character=base_char,
        )

    def validate_corrections(
        self,
        raw_text: str,
        corrections: List[CorrectionItem],
        valid_block_ids: Optional[Set[str]] = None,
        char_mapping: Optional[List[Dict[str, Any]]] = None,
        source_revision: Optional[int] = None,
        current_revision: Optional[int] = None,
        max_edit_ratio: float = 0.5,
    ) -> Tuple[List[CorrectionItem], List[Dict[str, Any]]]:
        """
        Validates a list of correction proposals.
        Returns (valid_corrections, rejected_proposals).
        Enforces:
        - Source revision freshness (rejects stale proposals if current_revision > source_revision)
        - Boundary and exact substring match
        - Non-overlapping spans
        - Block ID and line index provenance against char_mapping/page_blocks
        - Edit distance & paraphrasing guards
        - Injection defenses
        """
        valid: List[CorrectionItem] = []
        rejected: List[Dict[str, Any]] = []

        # 0. Check revision staleness
        if source_revision is not None and current_revision is not None and source_revision != current_revision:
            stale_items: List[CorrectionItem] = []
            for item in corrections:
                item.status = "stale"
                item.reason = f"Stale proposal: created for source_revision={source_revision} but document is currently at revision {current_revision}"
                stale_items.append(item)
                rejected.append({
                    "change_id": item.change_id,
                    "reason": item.reason,
                    "status": "stale",
                })
            return [], rejected

        # Sort proposals by start position
        sorted_proposals = sorted(corrections, key=lambda c: (c.start, c.end))
        last_end = -1

        for item in sorted_proposals:
            # 1. Bounds check
            if item.start < 0 or item.end > len(raw_text) or item.start >= item.end:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Out of bounds: [{item.start}, {item.end}) for text of length {len(raw_text)}"
                })
                continue

            # 2. Exact match check
            actual_sub = raw_text[item.start:item.end]
            if actual_sub != item.original_text:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Content mismatch: expected '{item.original_text}', found '{actual_sub}'"
                })
                continue

            # 3. Overlap check
            if item.start < last_end:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Overlapping span: start {item.start} is before previous end {last_end}"
                })
                continue

            # 4. Block ID existence check
            if valid_block_ids is not None and item.block_id not in valid_block_ids:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Invalid block_id '{item.block_id}' not found in page blocks"
                })
                continue

            # 4b. Char mapping line provenance verification
            if char_mapping is not None and len(char_mapping) > 0:
                mapping_match = False
                for m in char_mapping:
                    m_start = m.get("start", 0)
                    m_end = m.get("end", 0)
                    m_bid = m.get("block_id")
                    m_line = m.get("line_index")
                    if m_start <= item.start and item.end <= m_end:
                        if item.block_id == m_bid and (item.line_index is None or item.line_index == m_line):
                            mapping_match = True
                            item.line_index = m_line
                            break
                        elif item.block_id == m_bid:
                            item.line_index = m_line
                            mapping_match = True
                            break
                if not mapping_match:
                    # Check boundary overlap
                    for m in char_mapping:
                        if m.get("start", 0) <= item.start < m.get("end", 0):
                            if item.block_id == m.get("block_id"):
                                mapping_match = True
                                item.line_index = m.get("line_index")
                                break
                if not mapping_match:
                    rejected.append({
                        "change_id": item.change_id,
                        "reason": f"Block/Line mapping mismatch: span [{item.start}, {item.end}) with block '{item.block_id}' line '{item.line_index}' not found in char_mapping"
                    })
                    continue

            # 5. Token length & Paraphrasing Guard: OCR errors are word-level (<= 25 chars, <= 1 space)
            if len(item.original_text) > 25 or item.original_text.strip().count(" ") > 1:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Phrase-level replacement rejected (length={len(item.original_text)} > 25 or multiple words)"
                })
                continue

            lev = levenshtein_distance(item.original_text, item.corrected_text)
            max_allowed_dist = max(2, int(len(item.original_text) * max_edit_ratio))
            len_diff = abs(len(item.original_text) - len(item.corrected_text))

            if lev > max_allowed_dist or len_diff > 3:
                rejected.append({
                    "change_id": item.change_id,
                    "reason": f"Edit distance too large (dist={lev}, max_allowed={max_allowed_dist}, len_diff={len_diff})"
                })
                continue

            # 6. Adversarial injection / command defense
            is_injected = False
            for pat in INJECTION_KEYWORDS:
                if pat.search(item.corrected_text) or pat.search(item.reason):
                    rejected.append({
                        "change_id": item.change_id,
                        "reason": "Rejected potential prompt injection keyword in output"
                    })
                    is_injected = True
                    break
            if is_injected:
                continue

            # 7. Check if target is number or named entity
            has_digits = bool(DIGIT_PATTERN.search(item.original_text) or DIGIT_PATTERN.search(item.corrected_text))
            if has_digits or item.category in ("number", "named_entity"):
                item.is_named_entity_or_number = True

            # 8. Calculate UI highlight span
            item.ui_highlight = self.calculate_ui_highlight(raw_text, item.start, item.end)

            valid.append(item)
            last_end = item.end

        return valid, rejected
