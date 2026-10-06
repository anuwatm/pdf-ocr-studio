import base64
import ctypes
import json
import statistics
import threading
import time
from ctypes import wintypes
from pathlib import Path

from src.epub_exporter import build_epub, prepare_epub_preview
from src.toc_editor import editor_state


ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "tests/artifacts"
JOB = "approved_44pages_job"
BUDGET = {"locked_at":"2026-10-06", "preview_p95_seconds":5.0, "package_p95_seconds":5.0,
          "peak_rss_mb":256.0, "runs":10, "scope":"approved 44-page HTML + saved Phase 9 TOC + PNG cover"}


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in
        ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage",
         "QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]


def peak_rss():
    counters=MemoryCounters(); counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL("kernel32"); kernel.GetCurrentProcess.restype=wintypes.HANDLE
    fn=ctypes.WinDLL("psapi").GetProcessMemoryInfo
    fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD]
    if not fn(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb): raise ctypes.WinError()
    return counters.PeakWorkingSetSize


def percentile(values, quantile):
    return statistics.quantiles(values, n=100, method="inclusive")[int(quantile*100)-1]


def main():
    phase = ROOT / "phase9"; phase.mkdir(exist_ok=True)
    (phase/"benchmark_budget.json").write_text(json.dumps(BUDGET,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    state=editor_state(JOB,str(FILES),"basic","page")
    cover={"data_base64":base64.b64encode((ROOT/"demo/01.png").read_bytes()).decode(),"alt":"ปกจาก demo/01.png"}
    previews=[]; packages=[]; peak=[0]; stop=threading.Event()
    def sample():
        while not stop.wait(.005): peak[0]=max(peak[0],peak_rss())
    sampler=threading.Thread(target=sample); sampler.start()
    try:
        for _ in range(BUDGET["runs"]):
            started=time.perf_counter(); meta=prepare_epub_preview(JOB,"basic",{"title":"Phase 9"},"page",str(FILES),cover,state["toc_revision"]); previews.append(time.perf_counter()-started)
            started=time.perf_counter(); build_epub(JOB,meta["preview_revision"],str(FILES)); packages.append(time.perf_counter()-started)
    finally:
        stop.set(); sampler.join()
    peak[0]=max(peak[0],peak_rss())
    report={"budget":BUDGET,"preview":{"p50":round(statistics.median(previews),4),"p95":round(percentile(previews,.95),4),"samples":previews},
            "package":{"p50":round(statistics.median(packages),4),"p95":round(percentile(packages,.95),4),"samples":packages},
            "peak_rss_mb":round(peak[0]/1024**2,2)}
    report["budget_pass"]=report["preview"]["p95"]<=5 and report["package"]["p95"]<=5 and report["peak_rss_mb"]<=256
    (phase/"benchmark_results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__": main()
