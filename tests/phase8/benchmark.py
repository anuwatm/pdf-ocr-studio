"""Measured EPUB benchmark from approved demo OCR output; budgets locked first."""
import json
import os
from pathlib import Path
import statistics
import threading
import time
import ctypes
from ctypes import wintypes
from src.epub_exporter import prepare_epub_preview, build_epub

BUDGET = {'preview_p95_seconds': 5, 'package_p95_seconds': 5, 'peak_rss_mb': 256,
          'runs_per_scenario': 10, 'pages': [44], 'source': 'approved demo/01.pdf-04.pdf and 01.png-02.png OCR output; no OCR/AI rerun'}
ROOT = Path('tests/artifacts').resolve()

class MemoryCounters(ctypes.Structure):
    _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]

def peak_rss():
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    memory_info = ctypes.WinDLL('psapi').GetProcessMemoryInfo
    memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    if not memory_info(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize

def percentile(values, p):
    ordered = sorted(values)
    x = (len(ordered)-1) * p
    low = int(x)
    high = min(low+1,len(ordered)-1)
    return ordered[low] + (ordered[high]-ordered[low])*(x-low)

def main():
    Path('phase8/benchmark_budget.json').write_text(json.dumps(BUDGET, indent=2), encoding='utf-8')
    peak = [0]
    stop = threading.Event()
    def sample():
        while not stop.wait(.005):
            peak[0] = max(peak[0], peak_rss())
    sampler = threading.Thread(target=sample)
    sampler.start()
    scenarios = []
    try:
        for pages in BUDGET['pages']:
            preview_times, package_times = [], []
            for iteration in range(BUDGET['runs_per_scenario']):
                job = 'approved_44pages_job'
                export = ROOT / job / 'export'
                if not (export/'basic.html').is_file():
                    raise RuntimeError('Approved 44-page HTML output is required; no synthetic replacement permitted')
                start = time.perf_counter()
                meta = prepare_epub_preview(job, source_variant='basic', chapter_split='page', files_dir=str(ROOT))
                preview_times.append(time.perf_counter()-start)
                start = time.perf_counter()
                package = build_epub(job, meta['preview_revision'], files_dir=str(ROOT))
                package_times.append(time.perf_counter()-start)
            summary = {'pages':pages, 'chapters':meta['chapters_count'], 'file_bytes':package['file_size']}
            for label, values in [('preview',preview_times),('package',package_times)]:
                summary[label] = {f'p{int(p*100)}_seconds':round(percentile(values,p),4) for p in (.5,.9,.95)}
                summary[label]['samples_seconds'] = values
            summary['time_budget_pass'] = summary['preview']['p95_seconds'] <= 5 and summary['package']['p95_seconds'] <= 5
            scenarios.append(summary)
    finally:
        stop.set()
        sampler.join()
    peak[0] = max(peak[0], peak_rss())
    report = {'budget':BUDGET, 'scenarios':scenarios, 'peak_rss_mb':round(peak[0]/1024**2,2),
              'memory_sampling_ms':5, 'memory_budget_pass':peak[0] <=256*1024**2,
              'note':'Approved 44-page export benchmark; not OCR throughput or reader benchmark'}
    Path('phase8/benchmark_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__ == '__main__':
    main()
