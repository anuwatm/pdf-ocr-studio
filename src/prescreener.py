"""
Phase 3 Prescreener: Suspicious Spot Identification.
Uses Thai orthography rules, illegal character sequences, and common OCR error patterns
to locate suspect tokens for targeted AI examination or screening.
"""
from typing import List, Dict, Any, Tuple
import re
import unicodedata

# Thai Unicode blocks
# Consonants: \u0e01-\u0e2e
# Leading Vowels: \u0e40-\u0e44 (เ, แ, โ, ใ, ไ)
# Upper Vowels: \u0e31, \u0e34-\u0e37 (ั, ิ, ี, ึ, ื)
# Lower Vowels: \u0e38-\u0e39 (ุ, ู)
# Following Vowels: \u0e30, \u0e32, \u0e33 (ะ, า, ำ)
# Tone Marks: \u0e48-\u0e4b (่, ้, ๊, ๋)
# Marks: \u0e4c-\u0e4e (์, ๎, ๏), \u0e47 (็), \u0e46 (ๆ)

# Suspicious patterns in Thai text
SUSPICIOUS_PATTERNS = [
    # Double tone marks
    (re.compile(r"[\u0e48-\u0e4b]{2,}"), "double_tone_mark"),
    # Double upper vowels
    (re.compile(r"[\u0e31\u0e34-\u0e37]{2,}"), "double_upper_vowel"),
    # Double lower vowels
    (re.compile(r"[\u0e38\u0e39]{2,}"), "double_lower_vowel"),
    # Tone mark before upper vowel (invalid order)
    (re.compile(r"[\u0e48-\u0e4b][\u0e31\u0e34-\u0e37]"), "inverted_tone_vowel"),
    # Leading vowel immediately followed by space or punctuation
    (re.compile(r"[\u0e40-\u0e44][\s,.\-!?]"), "orphan_leading_vowel"),
    # Double sara e used instead of sara ae
    (re.compile(r"\u0e40\u0e40"), "double_sara_e"),
    # Common OCR misspelling candidates
    (re.compile(r"วันที(?=[\s\d]|$)"), "missing_mai_ek"),
    (re.compile(r"อนุญาติ"), "superfluous_vowel"),
    (re.compile(r"เพือ(?=[\s\u0e01-\u0e2e]|$)"), "missing_mai_ek"),
    (re.compile(r"อยาง(?=[\s\u0e01-\u0e2e]|$)"), "missing_mai_ek"),
    (re.compile(r"พดโวยวาย"), "missing_vowel"),
    (re.compile(r"ป้ามี่(?=[\s\u0e01-\u0e2e]|$)"), "confused_consonant"),
    (re.compile(r"เทคโนโลยี่"), "superfluous_tone"),
]

# Common Thai OCR substitution pairs (high precision rules)
HIGH_PRECISION_CORRECTIONS = {
    "วันที": ("วันที่", "vowel_tone", "Missing mai-ek on 'วันที'"),
    "อนุญาติ": ("อนุญาต", "spelling", "Superfluous sara-i on 'อนุญาติ'"),
    "เพือ": ("เพื่อ", "vowel_tone", "Missing mai-ek on 'เพือ'"),
    "อยาง": ("อย่าง", "vowel_tone", "Missing mai-ek on 'อยาง'"),
    "เทคโนโลยี่": ("เทคโนโลยี", "vowel_tone", "Superfluous mai-ek on 'เทคโนโลยี่'"),
    "พดโวยวาย": ("พูดโวยวาย", "vowel_tone", "Missing sara-uu on 'พดโวยวาย'"),
    "ป้ามี่": ("ป้าที่", "spelling", "OCR confusion: มี่ -> ที่"),
}


def find_suspicious_spots(text: str) -> List[Dict[str, Any]]:
    """
    Scans text for suspicious spots using regex and orthography checks.
    Returns list of suspect occurrences with their exact [start, end) offsets.
    """
    spots = []
    seen_ranges = set()

    for pattern, reason in SUSPICIOUS_PATTERNS:
        for m in pattern.finditer(text):
            span = m.span()
            if span not in seen_ranges:
                seen_ranges.add(span)
                spots.append({
                    "start": span[0],
                    "end": span[1],
                    "matched_text": m.group(0),
                    "reason": reason,
                    "suggested_correction": HIGH_PRECISION_CORRECTIONS.get(m.group(0), (None, None, None))[0]
                })

    return sorted(spots, key=lambda s: s["start"])
