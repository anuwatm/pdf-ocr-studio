import json
import os
import statistics
import time
import uuid
import ctypes
from ctypes import wintypes
from pathlib import Path

from src.pipeline import ProcessingPipeline
from src.structured_layout import generate_structured_exports


ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "demo" / "08.pdf").is_file():
    ROOT = ROOT.parent
DEMO = ROOT / "demo" / "08.pdf"
ARTIFACTS = Path.cwd() / "tests" / "artifacts" / "phase8_1_benchmark"
RESULT = Path.cwd() / "phase8_1" / "benchmark_results.json"


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percent)))
    return ordered[index]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def process_rss():
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    success = get_memory(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    if not success:
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    timings = []
    peak_rss = process_rss()
    table_counts = []
    job_id = "bench_" + uuid.uuid4().hex[:12]
    output = ARTIFACTS / job_id
    result = ProcessingPipeline(ocr_engine=object()).process_file(
        str(DEMO), job_id=job_id, output_dir=str(output)
    )
    table_count = sum(1 for page in result["pages"] for block in page["layout"]["blocks"]
                      if block["type"] == "table")
    for _ in range(10):
        started = time.perf_counter()
        generate_structured_exports(job_id, files_dir=str(ARTIFACTS))
        timings.append(time.perf_counter() - started)
        peak_rss = max(peak_rss, process_rss())
        table_counts.append(table_count)
    payload = {
        "dataset": "demo/08.pdf",
        "pages": 11,
        "runs": len(timings),
        "seconds": {
            "p50": round(statistics.median(timings), 4),
            "p90": round(percentile(timings, .90), 4),
            "p95": round(percentile(timings, .95), 4),
            "max": round(max(timings), 4),
        },
        "peak_process_rss_mb": round(peak_rss / 1024 / 1024, 2),
        "tables_per_run": table_counts,
        "budget_pass": percentile(timings, .95) <= 5.0 and peak_rss / 1024 / 1024 <= 256.0,
        "notes": "Measures Phase 8.1 export from saved OCR/layout artifact; OCR is intentionally outside this no-rerun path."
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
