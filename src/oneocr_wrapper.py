"""
OneOCR ctypes wrapper for Windows 11 Snipping Tool OCR engine
"""

import ctypes
import os
import copy
from ctypes import (
    Structure,
    byref,
    POINTER,
    c_int64,
    c_int32,
    c_float,
    c_ubyte,
    c_char,
    c_char_p,
    create_string_buffer,
)
from PIL import Image

MODEL_KEY = b"kj)TGtrK>f]b[Piow.gU+nC@s\"\"\"\"\"\"4"

c_int64_p = POINTER(c_int64)
c_float_p = POINTER(c_float)
c_ubyte_p = POINTER(c_ubyte)


class ImageStructure(Structure):
    """
    Image data structure matching win11-oneocr ABI
    sizeof(ImageStructure) == 32 (0x20) on x64
    """
    _fields_ = [
        ("type", c_int32),       # format type: 3 for BGRA 8-bit
        ("width", c_int32),      # image width in pixels
        ("height", c_int32),     # image height in pixels
        ("_reserved", c_int32),  # 0
        ("step_size", c_int64),  # bytes per row (width * 4)
        ("data_ptr", c_ubyte_p), # pointer to BGRA buffer
    ]


class BoundingBox(Structure):
    """
    Text bounding box coordinates (4 corners)
    """
    _fields_ = [
        ("x1", c_float),
        ("y1", c_float),
        ("x2", c_float),
        ("y2", c_float),
        ("x3", c_float),
        ("y3", c_float),
        ("x4", c_float),
        ("y4", c_float),
    ]


BoundingBox_p = POINTER(BoundingBox)

DLL_FUNCTIONS = [
    ("CreateOcrInitOptions", [c_int64_p], c_int64),
    ("OcrInitOptionsSetUseModelDelayLoad", [c_int64, c_char], c_int64),
    ("CreateOcrPipeline", [c_char_p, c_char_p, c_int64, c_int64_p], c_int64),
    ("CreateOcrProcessOptions", [c_int64_p], c_int64),
    ("OcrProcessOptionsSetMaxRecognitionLineCount", [c_int64, c_int64], c_int64),
    ("RunOcrPipeline", [c_int64, POINTER(ImageStructure), c_int64, c_int64_p], c_int64),
    ("GetImageAngle", [c_int64, c_float_p], c_int64),
    ("GetOcrLineCount", [c_int64, c_int64_p], c_int64),
    ("GetOcrLine", [c_int64, c_int64, c_int64_p], c_int64),
    ("GetOcrLineContent", [c_int64, POINTER(c_char_p)], c_int64),
    ("GetOcrLineBoundingBox", [c_int64, POINTER(BoundingBox_p)], c_int64),
    ("GetOcrLineWordCount", [c_int64, c_int64_p], c_int64),
    ("GetOcrWord", [c_int64, c_int64, c_int64_p], c_int64),
    ("GetOcrWordContent", [c_int64, POINTER(c_char_p)], c_int64),
    ("GetOcrWordBoundingBox", [c_int64, POINTER(BoundingBox_p)], c_int64),
    ("GetOcrWordConfidence", [c_int64, c_float_p], c_int64),
    ("ReleaseOcrResult", [c_int64], None),
    ("ReleaseOcrInitOptions", [c_int64], None),
    ("ReleaseOcrPipeline", [c_int64], None),
    ("ReleaseOcrProcessOptions", [c_int64], None),
]


class OneOcrEngine:
    def __init__(self, dll_dir: str = None):
        import sys
        if sys.maxsize <= 2**32:
            raise RuntimeError("OneOCR requires a 64-bit Python environment.")

        if dll_dir is None:
            self.dll_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "oneOCR"))
        else:
            self.dll_dir = os.path.abspath(dll_dir)

        self.dll_path = os.path.join(self.dll_dir, "oneocr.dll")
        self.model_path = os.path.join(self.dll_dir, "oneocr.onemodel")
        self.onnx_path = os.path.join(self.dll_dir, "onnxruntime.dll")

        self.ocr_dll = None
        self.init_options = None
        self.pipeline = None
        self.process_options = None
        self._dll_dir_cookie = None

        if not os.path.exists(self.dll_path):
            raise FileNotFoundError(f"DLL not found: {self.dll_path}")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        self._load_dll()
        self._init_pipeline()

    def _load_dll(self):
        # On Windows Python 3.8+, register DLL directory so onnxruntime.dll is found
        if hasattr(os, "add_dll_directory"):
            self._dll_dir_cookie = os.add_dll_directory(self.dll_dir)

        # Also call SetDllDirectoryW as fallback
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            if hasattr(kernel32, "SetDllDirectoryW"):
                kernel32.SetDllDirectoryW(self.dll_dir)
        except Exception:
            pass

        self.ocr_dll = ctypes.WinDLL(self.dll_path)

        for name, argtypes, restype in DLL_FUNCTIONS:
            try:
                func = getattr(self.ocr_dll, name)
                func.argtypes = argtypes
                func.restype = restype
            except AttributeError as e:
                raise RuntimeError(f"Missing DLL export function: {name}") from e

    def _init_pipeline(self):
        # 1. Init Options
        init_opt = c_int64(0)
        res = self.ocr_dll.CreateOcrInitOptions(byref(init_opt))
        if res != 0 or init_opt.value == 0:
            raise RuntimeError(f"CreateOcrInitOptions failed with code: {res}")
        self.init_options = init_opt.value

        res = self.ocr_dll.OcrInitOptionsSetUseModelDelayLoad(self.init_options, 0)
        if res != 0:
            raise RuntimeError(f"OcrInitOptionsSetUseModelDelayLoad failed with code: {res}")

        # 2. Pipeline
        pipeline = c_int64(0)
        model_buf = create_string_buffer(self.model_path.encode("utf-8"))
        key_buf = create_string_buffer(MODEL_KEY)
        res = self.ocr_dll.CreateOcrPipeline(model_buf, key_buf, self.init_options, byref(pipeline))
        if res != 0 or pipeline.value == 0:
            raise RuntimeError(f"CreateOcrPipeline failed with code: {res}")
        self.pipeline = pipeline.value

        # 3. Process Options
        proc_opt = c_int64(0)
        res = self.ocr_dll.CreateOcrProcessOptions(byref(proc_opt))
        if res != 0 or proc_opt.value == 0:
            raise RuntimeError(f"CreateOcrProcessOptions failed with code: {res}")
        self.process_options = proc_opt.value

        res = self.ocr_dll.OcrProcessOptionsSetMaxRecognitionLineCount(self.process_options, 1000)
        if res != 0:
            raise RuntimeError(f"OcrProcessOptionsSetMaxRecognitionLineCount failed with code: {res}")

    def recognize_pil(self, image: Image.Image) -> dict:
        """
        Process a PIL Image object and return OCR result dictionary
        """
        if image is None or not isinstance(image, Image.Image):
            raise TypeError(f"Invalid image type: expected PIL.Image.Image, got {type(image)}")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image dimensions: {width}x{height}")
        if width < 10 or height < 10 or width > 10000 or height > 10000:
            raise ValueError(f"Image dimensions ({width}x{height}) out of supported range (10x10 to 10000x10000)")

        # Convert to RGBA
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Convert to BGRA (OneOCR expects BGRA)
        r, g, b, a = image.split()
        bgra_image = Image.merge("RGBA", (b, g, r, a))
        raw_bytes = bgra_image.tobytes()

        # Keep buffer alive during call
        buf_len = len(raw_bytes)
        c_buffer = (c_ubyte * buf_len).from_buffer_copy(raw_bytes)
        step_size = width * 4

        img_struct = ImageStructure(
            type=3,
            width=width,
            height=height,
            _reserved=0,
            step_size=step_size,
            data_ptr=ctypes.cast(c_buffer, c_ubyte_p),
        )

        ocr_result = c_int64(0)
        res = self.ocr_dll.RunOcrPipeline(
            self.pipeline,
            byref(img_struct),
            self.process_options,
            byref(ocr_result),
        )

        if res != 0 or ocr_result.value == 0:
            return {"text": "", "lines": [], "error": f"RunOcrPipeline failed with code: {res}"}

        try:
            return self._parse_results(ocr_result.value)
        finally:
            self.ocr_dll.ReleaseOcrResult(ocr_result.value)
            del c_buffer
            del raw_bytes
            del bgra_image

    def _parse_results(self, result_handle: int) -> dict:
        text_angle = c_float(0.0)
        angle_res = self.ocr_dll.GetImageAngle(result_handle, byref(text_angle))
        angle_val = text_angle.value if angle_res == 0 else 0.0

        line_count = c_int64(0)
        res = self.ocr_dll.GetOcrLineCount(result_handle, byref(line_count))
        if res != 0:
            return {"text": "", "text_angle": angle_val, "lines": []}

        lines = []
        for line_idx in range(line_count.value):
            line_handle = c_int64(0)
            if self.ocr_dll.GetOcrLine(result_handle, line_idx, byref(line_handle)) != 0:
                continue

            line_text = self._get_text(line_handle.value, self.ocr_dll.GetOcrLineContent)
            line_bbox = self._get_bbox(line_handle.value, self.ocr_dll.GetOcrLineBoundingBox)

            words = []
            word_count = c_int64(0)
            if self.ocr_dll.GetOcrLineWordCount(line_handle.value, byref(word_count)) == 0:
                for w_idx in range(word_count.value):
                    w_handle = c_int64(0)
                    if self.ocr_dll.GetOcrWord(line_handle.value, w_idx, byref(w_handle)) == 0:
                        w_text = self._get_text(w_handle.value, self.ocr_dll.GetOcrWordContent)
                        w_bbox = self._get_bbox(w_handle.value, self.ocr_dll.GetOcrWordBoundingBox)
                        w_conf = c_float(0.0)
                        conf_res = self.ocr_dll.GetOcrWordConfidence(w_handle.value, byref(w_conf))
                        conf_val = w_conf.value if conf_res == 0 else None
                        words.append({
                            "text": w_text,
                            "bbox": w_bbox,
                            "confidence": conf_val,
                        })

            lines.append({
                "line_index": line_idx,
                "text": line_text,
                "bbox": line_bbox,
                "words": words,
            })

        full_text = "\n".join(l["text"] for l in lines if l["text"] is not None)
        return {
            "text": full_text,
            "text_angle": angle_val,
            "lines": lines,
        }

    def _get_text(self, handle: int, getter_func) -> str:
        content_ptr = c_char_p()
        if getter_func(handle, byref(content_ptr)) == 0 and content_ptr.value:
            return content_ptr.value.decode("utf-8", errors="ignore")
        return ""

    def _get_bbox(self, handle: int, getter_func) -> dict:
        bbox_ptr = BoundingBox_p()
        if getter_func(handle, byref(bbox_ptr)) == 0 and bbox_ptr:
            b = bbox_ptr.contents
            return {
                "x1": round(b.x1, 2),
                "y1": round(b.y1, 2),
                "x2": round(b.x2, 2),
                "y2": round(b.y2, 2),
                "x3": round(b.x3, 2),
                "y3": round(b.y3, 2),
                "x4": round(b.x4, 2),
                "y4": round(b.y4, 2),
            }
        return None

    def close(self):
        ocr_dll = getattr(self, "ocr_dll", None)
        if ocr_dll:
            proc_opt = getattr(self, "process_options", None)
            if proc_opt:
                try:
                    ocr_dll.ReleaseOcrProcessOptions(proc_opt)
                except Exception:
                    pass
                self.process_options = None
            pipeline = getattr(self, "pipeline", None)
            if pipeline:
                try:
                    ocr_dll.ReleaseOcrPipeline(pipeline)
                except Exception:
                    pass
                self.pipeline = None
            init_opt = getattr(self, "init_options", None)
            if init_opt:
                try:
                    ocr_dll.ReleaseOcrInitOptions(init_opt)
                except Exception:
                    pass
                self.init_options = None

    def __del__(self):
        self.close()
