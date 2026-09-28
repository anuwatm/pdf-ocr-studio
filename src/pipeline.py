"""
Pipeline module for Local Thai OCR Web (Phase 2)
Coordinates file detection, PDF/Image inspection, multi-signal routing,
hybrid masking, OneOCR execution, reading order, Thai text assembly,
Schema 2.0.0 JSON generation, and verified UTF-8 raw text output.
"""

import os
import json
import uuid
import re
from typing import Dict, List, Optional, Any, Tuple, Union, Set
from PIL import Image, ImageOps, ImageDraw
import fitz  # PyMuPDF

from .file_detector import validate_file, FileValidationResult
from .geometry import Rect, AffineTransform, quad_to_rect
from .pdf_extractor import (
    inspect_pdf_page,
    render_pdf_page_to_image,
    extract_native_text_blocks,
    check_visual_blank,
)
from .text_assembler import (
    assemble_page_text,
    sort_blocks_reading_order,
    detect_and_format_table_lines,
    CharSpanMapping,
)
from .oneocr_wrapper import OneOcrEngine

SCHEMA_VERSION = "2.0.0"
PAGE_SEPARATOR_TEMPLATE = "\n\n--- Page {page_number} ---\n\n"
PAGE_SEPARATOR_BLANK = "\n\n--- Page {page_number} [BLANK] ---\n\n"
PAGE_SEPARATOR_EMPTY = "\n\n--- Page {page_number} [NO_TEXT_FOUND] ---\n\n"
PAGE_SEPARATOR_FAILED = "\n\n--- Page {page_number} [FAILED: {error}] ---\n\n"


class ProcessingPipeline:
    def __init__(self, ocr_engine: Optional[OneOcrEngine] = None, dll_dir: Optional[str] = None):
        self._owned_engine = False
        if ocr_engine is not None:
            self.engine = ocr_engine
        else:
            self.engine = OneOcrEngine(dll_dir=dll_dir)
            self._owned_engine = True

    def close(self):
        if self._owned_engine and self.engine:
            self.engine.close()
            self.engine = None

    def __del__(self):
        self.close()

    def process_file(
        self,
        file_path: str,
        job_id: Optional[str] = None,
        dpi: int = 300,
        output_dir: Optional[str] = None,
        page_range: Optional[Union[Tuple[int, int], List[int], range]] = None,
        enable_ai_correction: bool = False,
        ai_corrector: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Process any supported file (PDF, PNG, JPG), executing routing, OCR,
        text assembly, and generating Schema 2.0.0 data structure.
        Supports page_range: (start_page, end_page) 1-indexed inclusive, or list of pages.
        Supports optional Phase 3 AI text correction (enable_ai_correction=True).
        """
        if not job_id:
            job_id = f"job_{uuid.uuid4().hex[:12]}"

        # 1. File detection & validation
        validation = validate_file(file_path)
        if not validation.valid:
            return {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "status": "failed",
                "error": validation.error,
                "file_info": {
                    "filename": os.path.basename(file_path),
                    "file_type": validation.file_type,
                    "size_bytes": validation.size_bytes,
                    "sha256": validation.sha256,
                    "total_pages": 0,
                    "processed_pages": 0,
                    "page_range": list(page_range) if isinstance(page_range, (tuple, list, range)) else None,
                },
                "pages": [],
                "raw_text": "",
            }

        # 2. Process based on type
        if validation.file_type == "pdf":
            result = self._process_pdf(file_path, validation, job_id, dpi, page_range=page_range)
        else:
            result = self._process_raster_image(file_path, validation, job_id, page_range=page_range)

        # 2.5 Optional Phase 3 AI text correction
        if enable_ai_correction:
            from .ai_corrector import AICorrector
            corrector = ai_corrector or AICorrector()
            corrected_text, changes_doc = corrector.correct_text(
                raw_text=result["raw_text"],
                job_id=job_id,
            )
            result["corrected_text"] = corrected_text
            result["changes_doc"] = changes_doc.model_dump()

        # 3. Output persistence if requested
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            raw_path = os.path.join(output_dir, "raw.txt")
            json_path = os.path.join(output_dir, "ocr.json")

            raw_content = result["raw_text"]
            with open(raw_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(raw_content)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            # 4. Verify 100% roundtrip UTF-8 integrity
            with open(raw_path, "r", encoding="utf-8") as f:
                readback_raw = f.read()
            if readback_raw != raw_content:
                raise IOError("UTF-8 verification failed for raw.txt: readback content differs from in-memory text")

            with open(json_path, "r", encoding="utf-8") as f:
                readback_json = json.load(f)
            if readback_json["job_id"] != result["job_id"] or len(readback_json["pages"]) != len(result["pages"]):
                raise IOError("UTF-8 verification failed for ocr.json: structure mismatch on readback")

            result["output_files"] = {
                "raw_txt": os.path.abspath(raw_path),
                "ocr_json": os.path.abspath(json_path),
            }

            # Optional Phase 3 AI output files
            if enable_ai_correction and "corrected_text" in result:
                corr_path = os.path.join(output_dir, "corrected.txt")
                changes_path = os.path.join(output_dir, "changes.json")
                with open(corr_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(result["corrected_text"])
                with open(changes_path, "w", encoding="utf-8") as f:
                    json.dump(result["changes_doc"], f, ensure_ascii=False, indent=2)

                # Readback verification
                with open(corr_path, "r", encoding="utf-8") as f:
                    if f.read() != result["corrected_text"]:
                        raise IOError("UTF-8 verification failed for corrected.txt")

                result["output_files"]["corrected_txt"] = os.path.abspath(corr_path)
                result["output_files"]["changes_json"] = os.path.abspath(changes_path)

        return result

    def _process_pdf(
        self,
        file_path: str,
        validation: FileValidationResult,
        job_id: str,
        dpi: int,
        page_range: Optional[Union[Tuple[int, int], List[int], range]] = None,
    ) -> Dict[str, Any]:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        pages_data = []
        raw_text_parts = []

        if page_range is None:
            target_page_indices = list(range(total_pages))
        elif isinstance(page_range, tuple) and len(page_range) == 2:
            start_p, end_p = page_range
            start_idx = max(0, start_p - 1)
            end_idx = min(total_pages, end_p)
            target_page_indices = list(range(start_idx, end_idx))
        elif isinstance(page_range, (list, set, range)):
            target_page_indices = sorted([p - 1 for p in page_range if 1 <= p <= total_pages])
        else:
            raise ValueError(f"Invalid page_range format: {page_range}. Expected Tuple[int, int] or List[int].")

        summary_counts = {
            "total_pages": total_pages,
            "processed_pages": len(target_page_indices),
            "completed": 0,
            "blank": 0,
            "failed": 0,
            "direct_text": 0,
            "ocr_image": 0,
            "hybrid": 0,
        }

        for pno in target_page_indices:
            page_id = pno + 1
            page = doc[pno]

            # Route page
            routing = inspect_pdf_page(page, page_id, dpi)

            # Render reference image to establish coordinate space
            ref_image = render_pdf_page_to_image(page, dpi=dpi)
            ref_w, ref_h = ref_image.size

            ref_meta = {
                "width": ref_w,
                "height": ref_h,
                "unit": "pixel",
                "origin": "top-left",
            }
            transform_meta = {
                "angle": 0.0,
                "scale_x": 1.0,
                "scale_y": 1.0,
                "translate_x": 0.0,
                "translate_y": 0.0,
            }

            if routing.decision == "blank":
                summary_counts["blank"] += 1
                page_record = {
                    "page_id": page_id,
                    "status": "blank",
                    "routing_decision": routing.decision,
                    "routing_reason": routing.reason,
                    "reference_image": ref_meta,
                    "transform": transform_meta,
                    "blocks": [],
                    "char_mapping": [],
                    "raw_text": "",
                }
                pages_data.append(page_record)
                raw_text_parts.append(PAGE_SEPARATOR_BLANK.format(page_number=page_id))
                continue

            elif routing.decision == "direct_text":
                summary_counts["direct_text"] += 1
                blocks = extract_native_text_blocks(page, dpi=dpi)
                page_text, mappings = assemble_page_text(page_id, blocks)

                summary_counts["completed"] += 1
                page_record = {
                    "page_id": page_id,
                    "status": "completed",
                    "routing_decision": routing.decision,
                    "routing_reason": routing.reason,
                    "reference_image": ref_meta,
                    "transform": transform_meta,
                    "blocks": self._clean_blocks_for_json(blocks),
                    "char_mapping": [m.to_dict() for m in mappings],
                    "raw_text": page_text,
                }
                pages_data.append(page_record)
                raw_text_parts.append(PAGE_SEPARATOR_TEMPLATE.format(page_number=page_id) + page_text)

            elif routing.decision == "ocr_image":
                summary_counts["ocr_image"] += 1
                ocr_result = self.engine.recognize_pil(ref_image)

                ocr_angle = ocr_result.get("text_angle", 0.0)
                transform_meta["angle"] = round(ocr_angle, 2)

                raw_lines = ocr_result.get("lines", [])
                if not raw_lines or not ocr_result.get("text", "").strip():
                    # Content existed (otherwise caught by blank), but engine returned empty
                    summary_counts["completed"] += 1
                    page_record = {
                        "page_id": page_id,
                        "status": "ocr_no_text_found",
                        "routing_decision": routing.decision,
                        "routing_reason": routing.reason,
                        "reference_image": ref_meta,
                        "transform": transform_meta,
                        "blocks": [],
                        "char_mapping": [],
                        "raw_text": "",
                    }
                    pages_data.append(page_record)
                    raw_text_parts.append(PAGE_SEPARATOR_EMPTY.format(page_number=page_id))
                    continue

                # Format table lines with tabs if structured
                lines_formatted = detect_and_format_table_lines(raw_lines)
                for l_dict, fmt_t in zip(raw_lines, lines_formatted):
                    l_dict["text"] = fmt_t

                # Convert lines into block format
                blocks = self._ocr_lines_to_blocks(page_id, raw_lines)
                page_text, mappings = assemble_page_text(page_id, blocks)

                summary_counts["completed"] += 1
                page_record = {
                    "page_id": page_id,
                    "status": "completed",
                    "routing_decision": routing.decision,
                    "routing_reason": routing.reason,
                    "reference_image": ref_meta,
                    "transform": transform_meta,
                    "blocks": self._clean_blocks_for_json(blocks),
                    "char_mapping": [m.to_dict() for m in mappings],
                    "raw_text": page_text,
                }
                pages_data.append(page_record)
                raw_text_parts.append(PAGE_SEPARATOR_TEMPLATE.format(page_number=page_id) + page_text)

            elif routing.decision == "hybrid":
                summary_counts["hybrid"] += 1
                native_blocks = extract_native_text_blocks(page, dpi=dpi)

                # Mask native text blocks on image copy to avoid duplicate OCR
                masked_image = ref_image.copy()
                draw = ImageDraw.Draw(masked_image)
                for nb in native_blocks:
                    rect = nb.get("rect")
                    if rect:
                        # Add slight margin to mask native text
                        draw.rectangle(
                            [rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2],
                            fill="white",
                        )

                # Run OCR on remaining non-native graphics
                ocr_result = self.engine.recognize_pil(masked_image)
                raw_lines = ocr_result.get("lines", [])
                ocr_blocks = self._ocr_lines_to_blocks(page_id, raw_lines, id_prefix="ocr")

                # Merge and sort
                combined_blocks = sort_blocks_reading_order(native_blocks + ocr_blocks)
                page_text, mappings = assemble_page_text(page_id, combined_blocks)

                summary_counts["completed"] += 1
                page_record = {
                    "page_id": page_id,
                    "status": "completed",
                    "routing_decision": routing.decision,
                    "routing_reason": routing.reason,
                    "reference_image": ref_meta,
                    "transform": transform_meta,
                    "blocks": self._clean_blocks_for_json(combined_blocks),
                    "char_mapping": [m.to_dict() for m in mappings],
                    "raw_text": page_text,
                }
                pages_data.append(page_record)
                raw_text_parts.append(PAGE_SEPARATOR_TEMPLATE.format(page_number=page_id) + page_text)

        doc.close()

        full_raw = "".join(raw_text_parts).lstrip("\n")

        overall_status = "completed"
        if summary_counts["failed"] > 0:
            overall_status = "partial" if summary_counts["completed"] > 0 else "failed"

        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "status": overall_status,
            "file_info": {
                "filename": os.path.basename(file_path),
                "file_type": validation.file_type,
                "size_bytes": validation.size_bytes,
                "sha256": validation.sha256,
                "total_pages": total_pages,
                "processed_pages": len(target_page_indices),
                "page_range": list(page_range) if isinstance(page_range, (tuple, list, range)) else None,
            },
            "summary": summary_counts,
            "pages": pages_data,
            "raw_text": full_raw,
        }

    def _process_raster_image(
        self,
        file_path: str,
        validation: FileValidationResult,
        job_id: str,
        page_range: Optional[Union[Tuple[int, int], List[int], range]] = None,
    ) -> Dict[str, Any]:
        # Raster images only have page 1
        should_process = True
        if page_range is not None:
            if isinstance(page_range, tuple) and len(page_range) == 2:
                should_process = (page_range[0] <= 1 <= page_range[1])
            elif isinstance(page_range, (list, set, range)):
                should_process = (1 in page_range)

        if not should_process:
            return {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "status": "completed",
                "file_info": {
                    "filename": os.path.basename(file_path),
                    "file_type": validation.file_type,
                    "size_bytes": validation.size_bytes,
                    "sha256": validation.sha256,
                    "total_pages": 1,
                    "processed_pages": 0,
                    "page_range": list(page_range) if isinstance(page_range, (tuple, list, range)) else None,
                },
                "summary": {
                    "total_pages": 1,
                    "processed_pages": 0,
                    "completed": 0,
                    "blank": 0,
                    "failed": 0,
                    "direct_text": 0,
                    "ocr_image": 0,
                    "hybrid": 0,
                },
                "pages": [],
                "raw_text": "",
            }
        with Image.open(file_path) as raw_img:
            # Handle EXIF orientation
            ref_image = ImageOps.exif_transpose(raw_img)
            if ref_image is None:
                ref_image = raw_img.copy()
            else:
                ref_image = ref_image.copy()

        ref_w, ref_h = ref_image.size
        page_id = 1

        ref_meta = {
            "width": ref_w,
            "height": ref_h,
            "unit": "pixel",
            "origin": "top-left",
        }
        transform_meta = {
            "angle": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "translate_x": 0.0,
            "translate_y": 0.0,
        }

        # Check if visually blank
        if check_visual_blank(ref_image):
            page_record = {
                "page_id": page_id,
                "status": "blank",
                "routing_decision": "blank",
                "routing_reason": "Raster image is visually blank / single color",
                "reference_image": ref_meta,
                "transform": transform_meta,
                "blocks": [],
                "char_mapping": [],
                "raw_text": "",
            }
            return {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "status": "completed",
                "file_info": {
                    "filename": os.path.basename(file_path),
                    "file_type": validation.file_type,
                    "size_bytes": validation.size_bytes,
                    "sha256": validation.sha256,
                    "total_pages": 1,
                },
                "summary": {
                    "total_pages": 1,
                    "completed": 0,
                    "blank": 1,
                    "failed": 0,
                    "direct_text": 0,
                    "ocr_image": 0,
                    "hybrid": 0,
                },
                "pages": [page_record],
                "raw_text": PAGE_SEPARATOR_BLANK.format(page_number=page_id).lstrip("\n"),
            }

        # Run OCR
        ocr_result = self.engine.recognize_pil(ref_image)
        ocr_angle = ocr_result.get("text_angle", 0.0)
        transform_meta["angle"] = round(ocr_angle, 2)

        raw_lines = ocr_result.get("lines", [])
        if not raw_lines or not ocr_result.get("text", "").strip():
            page_record = {
                "page_id": page_id,
                "status": "ocr_no_text_found",
                "routing_decision": "ocr_image",
                "routing_reason": "Image contains visual pixels but OneOCR returned empty text",
                "reference_image": ref_meta,
                "transform": transform_meta,
                "blocks": [],
                "char_mapping": [],
                "raw_text": "",
            }
            return {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "status": "completed",
                "file_info": {
                    "filename": os.path.basename(file_path),
                    "file_type": validation.file_type,
                    "size_bytes": validation.size_bytes,
                    "sha256": validation.sha256,
                    "total_pages": 1,
                },
                "summary": {
                    "total_pages": 1,
                    "completed": 1,
                    "blank": 0,
                    "failed": 0,
                    "direct_text": 0,
                    "ocr_image": 1,
                    "hybrid": 0,
                },
                "pages": [page_record],
                "raw_text": PAGE_SEPARATOR_EMPTY.format(page_number=page_id).lstrip("\n"),
            }

        blocks = self._ocr_lines_to_blocks(page_id, raw_lines)
        page_text, mappings = assemble_page_text(page_id, blocks)

        page_record = {
            "page_id": page_id,
            "status": "completed",
            "routing_decision": "ocr_image",
            "routing_reason": "Raster image processed through OneOCR engine",
            "reference_image": ref_meta,
            "transform": transform_meta,
            "blocks": self._clean_blocks_for_json(blocks),
            "char_mapping": [m.to_dict() for m in mappings],
            "raw_text": page_text,
        }

        full_raw = PAGE_SEPARATOR_TEMPLATE.format(page_number=page_id) + page_text
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "status": "completed",
            "file_info": {
                "filename": os.path.basename(file_path),
                "file_type": validation.file_type,
                "size_bytes": validation.size_bytes,
                "sha256": validation.sha256,
                "total_pages": 1,
                "processed_pages": 1,
                "page_range": list(page_range) if isinstance(page_range, (tuple, list, range)) else None,
            },
            "summary": {
                "total_pages": 1,
                "processed_pages": 1,
                "completed": 1,
                "blank": 0,
                "failed": 0,
                "direct_text": 0,
                "ocr_image": 1,
                "hybrid": 0,
            },
            "pages": [page_record],
            "raw_text": full_raw.lstrip("\n"),
        }

    def process_file_in_batches(
        self,
        file_path: str,
        batch_size: int = 100,
        job_id_prefix: Optional[str] = None,
        dpi: int = 300,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a large document (e.g. 400+ pages) in controlled chunks of `batch_size` pages
        (default 100 pages) to strictly adhere to memory budgets and ceiling limits.
        If output_dir is provided, saves per-batch outputs and combined raw.txt.
        """
        validation = validate_file(file_path)
        if not validation.valid:
            raise ValueError(f"Cannot batch process invalid file: {validation.error}")

        if validation.file_type != "pdf":
            single_res = self.process_file(file_path, job_id=job_id_prefix, dpi=dpi, output_dir=output_dir)
            return {
                "total_pages": 1,
                "total_batches": 1,
                "batches": [single_res],
                "combined_raw_text": single_res["raw_text"],
            }

        doc = fitz.open(file_path)
        total_pages = len(doc)
        doc.close()

        if not job_id_prefix:
            job_id_prefix = f"batch_{uuid.uuid4().hex[:8]}"

        batch_results = []
        combined_raw_parts = []
        batch_num = 1

        for start_p in range(1, total_pages + 1, batch_size):
            end_p = min(total_pages, start_p + batch_size - 1)
            b_job_id = f"{job_id_prefix}_b{batch_num:02d}_p{start_p}_{end_p}"
            b_out_dir = os.path.join(output_dir, f"batch_{batch_num:02d}") if output_dir else None

            b_res = self.process_file(
                file_path=file_path,
                job_id=b_job_id,
                dpi=dpi,
                output_dir=b_out_dir,
                page_range=(start_p, end_p),
            )
            batch_results.append(b_res)
            if b_res.get("raw_text"):
                combined_raw_parts.append(b_res["raw_text"])
            batch_num += 1

        combined_raw = "\n\n".join(combined_raw_parts).strip()

        if output_dir:
            combined_raw_path = os.path.join(output_dir, "raw.txt")
            with open(combined_raw_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(combined_raw)

            combined_summary_path = os.path.join(output_dir, "batch_manifest.json")
            manifest = {
                "file": os.path.basename(file_path),
                "total_pages": total_pages,
                "batch_size": batch_size,
                "total_batches": len(batch_results),
                "batches": [
                    {
                        "batch": i + 1,
                        "job_id": b["job_id"],
                        "page_range": b["file_info"]["page_range"],
                        "pages_processed": len(b["pages"]),
                        "status": b["status"],
                    }
                    for i, b in enumerate(batch_results)
                ],
            }
            with open(combined_summary_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        return {
            "total_pages": total_pages,
            "total_batches": len(batch_results),
            "batches": batch_results,
            "combined_raw_text": combined_raw,
        }

    def _ocr_lines_to_blocks(
        self, page_id: int, lines: List[Dict[str, Any]], id_prefix: str = "b"
    ) -> List[Dict[str, Any]]:
        """
        Group OCR lines into paragraph/block units based on vertical distance.
        """
        if not lines:
            return []

        blocks = []
        curr_block_lines = []
        prev_y1 = None

        for idx, line in enumerate(lines):
            bbox = line.get("bbox")
            if not bbox:
                continue

            y0 = min(bbox["y1"], bbox["y2"])
            y1 = max(bbox["y3"], bbox["y4"])
            line_h = max(1.0, y1 - y0)

            # Check vertical gap between consecutive lines
            if prev_y1 is not None and (y0 - prev_y1) > (line_h * 1.5):
                # New block
                blocks.append(self._create_block_from_lines(page_id, len(blocks), curr_block_lines, id_prefix))
                curr_block_lines = []

            curr_block_lines.append(line)
            prev_y1 = y1

        if curr_block_lines:
            blocks.append(self._create_block_from_lines(page_id, len(blocks), curr_block_lines, id_prefix))

        return blocks

    def _create_block_from_lines(
        self, page_id: int, block_idx: int, lines: List[Dict[str, Any]], id_prefix: str
    ) -> Dict[str, Any]:
        all_xs = []
        all_ys = []
        for l in lines:
            b = l["bbox"]
            all_xs.extend([b["x1"], b["x2"], b["x3"], b["x4"]])
            all_ys.extend([b["y1"], b["y2"], b["y3"], b["y4"]])

        min_x, max_x = min(all_xs), max(all_xs)
        min_y, max_y = min(all_ys), max(all_ys)

        quad = [
            round(min_x, 2), round(min_y, 2),
            round(max_x, 2), round(min_y, 2),
            round(max_x, 2), round(max_y, 2),
            round(min_x, 2), round(max_y, 2),
        ]

        for l_idx, l in enumerate(lines):
            l["line_index"] = l_idx

        text = "\n".join(l.get("text", "") for l in lines)
        return {
            "block_id": f"p{page_id}_{id_prefix}{block_idx}",
            "source": "ocr",
            "confidence": None,
            "bbox": {
                "x1": quad[0], "y1": quad[1],
                "x2": quad[2], "y2": quad[3],
                "x3": quad[4], "y3": quad[5],
                "x4": quad[6], "y4": quad[7],
            },
            "rect": Rect(min_x, min_y, max_x, max_y),
            "text": text,
            "lines": lines,
        }

    def _clean_blocks_for_json(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove non-serializable objects like Rect before JSON dump."""
        cleaned = []
        for b in blocks:
            c = dict(b)
            if "rect" in c:
                del c["rect"]
            cleaned.append(c)
        return cleaned
