"""Bounded CLI pipes and cancellation of the complete process tree."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time


class CliCancelledError(RuntimeError):
    code = "cancelled"


class CliOutputError(RuntimeError):
    code = "invalid_response"


def _windows_job(process):
    """A kill-on-close Job Object also owns descendants that inherit pipes."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or
            not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return lambda: kernel.CloseHandle(job)


def run_cli_process(command, *, input_text=None, timeout=60, cwd=None, env=None,
                    cancel_event=None, max_output_bytes=5 * 1024 * 1024):
    """Capture at most max_output_bytes across stdout AND stderr, in UTF-8."""
    if cancel_event is not None and cancel_event.is_set():
        raise CliCancelledError("AI CLI generation cancelled")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=False, cwd=cwd, env=env,
                               creationflags=flags, start_new_session=os.name != "nt")
    close_job = None
    streams = [bytearray(), bytearray()]
    overflow = threading.Event()
    pipe_error = threading.Event()
    lock = threading.Lock()
    total_bytes = 0
    deadline = time.monotonic() + timeout
    threads = []

    def stop_tree():
        nonlocal close_job
        if close_job is not None:
            close_job()
            close_job = None
        elif os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            # Only used if Job Object assignment failed before starting pipe threads.
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           shell=False, creationflags=flags, timeout=5)
        if process.poll() is None:
            process.kill()

    def read_pipe(pipe, index):
        nonlocal total_bytes
        try:
            while True:
                chunk = pipe.read1(4096)
                if not chunk:
                    return
                with lock:
                    total_bytes += len(chunk)
                    if total_bytes > max_output_bytes:
                        overflow.set()
                        return
                    streams[index].extend(chunk)
        except (OSError, ValueError):
            pipe_error.set()

    def write_input():
        try:
            if input_text is not None:
                process.stdin.write(input_text.encode("utf-8"))
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    try:
        if os.name == "nt":
            close_job = _windows_job(process)
        threads = [threading.Thread(target=read_pipe, args=(process.stdout, 0), daemon=True),
                   threading.Thread(target=read_pipe, args=(process.stderr, 1), daemon=True),
                   threading.Thread(target=write_input, daemon=True)]
        for thread in threads:
            thread.start()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                raise CliCancelledError("AI CLI generation cancelled")
            if overflow.is_set():
                raise CliOutputError("AI CLI stdout/stderr exceeded byte limit")
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.02)
        # Terminate descendants even when the parent exits before they close inherited pipes.
        stop_tree()
        for thread in threads:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in threads) or pipe_error.is_set():
            raise CliOutputError("AI CLI pipes did not close cleanly")
        if overflow.is_set():
            raise CliOutputError("AI CLI stdout/stderr exceeded byte limit")
        if cancel_event is not None and cancel_event.is_set():
            raise CliCancelledError("AI CLI generation cancelled")
        try:
            stdout, stderr = [bytes(value).decode("utf-8", errors="strict") for value in streams]
        except UnicodeDecodeError as exc:
            raise CliOutputError("AI CLI returned invalid UTF-8") from exc
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        stop_tree()
        process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()
