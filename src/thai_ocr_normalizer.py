"""High-precision normalization for recurring Thai OCR spacing errors."""

import re
import unicodedata


# When OCR splits the Thai vowel ำ into a space plus า, join it back to the
# preceding Thai consonant. The tone-mark version covers น ้า -> น้ำ.
_SPACE = r"[ \u00a0]+"
_THAI_CONSONANT = r"[\u0e01-\u0e2e]"
_SARA_AM_WITH_TONE = re.compile(rf"({_THAI_CONSONANT}){_SPACE}([\u0e48-\u0e4b])\u0e32")
_SARA_AM = re.compile(rf"({_THAI_CONSONANT}){_SPACE}\u0e32")


def normalize_ocr_line(text: str) -> str:
    """Repair Thai vowel ำ that OCR split with a space."""
    normalized = unicodedata.normalize("NFC", text).replace("\u200b", "").replace("\ufeff", "")
    normalized = _SARA_AM_WITH_TONE.sub(r"\1\2ำ", normalized)
    normalized = _SARA_AM.sub(r"\1ำ", normalized)
    return normalized
