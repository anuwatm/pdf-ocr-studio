"""
File detection and validation module for Local Thai OCR Web
Handles magic-byte inspection, MIME verification, format validation,
corruption detection, and encrypted PDF rejection.
"""

import os
import hashlib
from typing import Optional, Tuple
from dataclasses import dataclass
from PIL import Image
import fitz  # PyMuPDF


@dataclass
class FileValidationResult:
    valid: bool
    file_type: str  # 'pdf', 'png', 'jpeg', or 'unsupported'
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int = 0
    error: Optional[str] = None


PDF_MAGIC = b"%PDF-"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def detect_magic_type(header: bytes) -> str:
    if header.startswith(PDF_MAGIC):
        return "pdf"
    if header.startswith(PNG_MAGIC):
        return "png"
    if header.startswith(JPEG_MAGIC):
        return "jpeg"
    return "unsupported"


def validate_file(file_path: str) -> FileValidationResult:
    """
    Validate input file format, magic bytes, integrity, and password protection.
    Rejects unsupported files and password-protected PDFs immediately with clear messages.
    """
    if not os.path.exists(file_path):
        return FileValidationResult(
            valid=False,
            file_type="unsupported",
            mime_type="unknown",
            size_bytes=0,
            sha256="",
            error=f"File not found: {file_path}",
        )

    size = os.path.getsize(file_path)
    if size == 0:
        return FileValidationResult(
            valid=False,
            file_type="unsupported",
            mime_type="unknown",
            size_bytes=0,
            sha256="",
            error="Empty file (0 bytes)",
        )

    file_sha256 = compute_sha256(file_path)

    # Read header for magic byte inspection
    with open(file_path, "rb") as f:
        header = f.read(32)

    magic_type = detect_magic_type(header)

    if magic_type == "pdf":
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            return FileValidationResult(
                valid=False,
                file_type="pdf",
                mime_type="application/pdf",
                size_bytes=size,
                sha256=file_sha256,
                error=f"Corrupted or invalid PDF file: {str(e)}",
            )

        try:
            if doc.is_encrypted or doc.needs_pass:
                doc.close()
                return FileValidationResult(
                    valid=False,
                    file_type="pdf",
                    mime_type="application/pdf",
                    size_bytes=size,
                    sha256=file_sha256,
                    error="Password-protected PDF files are not supported in MVP. Please remove encryption before upload.",
                )
            page_count = len(doc)
            doc.close()
            return FileValidationResult(
                valid=True,
                file_type="pdf",
                mime_type="application/pdf",
                size_bytes=size,
                sha256=file_sha256,
                page_count=page_count,
            )
        except Exception as e:
            try:
                doc.close()
            except Exception:
                pass
            return FileValidationResult(
                valid=False,
                file_type="pdf",
                mime_type="application/pdf",
                size_bytes=size,
                sha256=file_sha256,
                error=f"Failed to inspect PDF structure: {str(e)}",
            )

    elif magic_type in ("png", "jpeg"):
        mime = "image/png" if magic_type == "png" else "image/jpeg"
        try:
            with Image.open(file_path) as img:
                img.verify()
            # Reopen to get dimensions and verify loadable
            with Image.open(file_path) as img:
                img.load()
                w, h = img.size
                if w <= 0 or h <= 0:
                    return FileValidationResult(
                        valid=False,
                        file_type=magic_type,
                        mime_type=mime,
                        size_bytes=size,
                        sha256=file_sha256,
                        error="Image has invalid dimensions (width <= 0 or height <= 0)",
                    )
            return FileValidationResult(
                valid=True,
                file_type=magic_type,
                mime_type=mime,
                size_bytes=size,
                sha256=file_sha256,
                page_count=1,
            )
        except Exception as e:
            return FileValidationResult(
                valid=False,
                file_type=magic_type,
                mime_type=mime,
                size_bytes=size,
                sha256=file_sha256,
                error=f"Corrupted or invalid image file ({magic_type}): {str(e)}",
            )

    else:
        ext = os.path.splitext(file_path)[1].lower()
        return FileValidationResult(
            valid=False,
            file_type="unsupported",
            mime_type="application/octet-stream",
            size_bytes=size,
            sha256=file_sha256,
            error=f"Unsupported file format (extension '{ext}', header magic {header[:8]!r}). Supported formats: PDF, PNG, JPG/JPEG.",
        )
