"""Serialize artifact writes and deletion for each job within this server."""
from contextlib import contextmanager
from functools import wraps
import os
import threading

_mutex = threading.Lock()
_locks = {}
_active = set()

def _key(job_id, files_dir):
    return os.path.normcase(os.path.realpath(os.path.join(files_dir, job_id)))

def is_artifact_busy(job_id, files_dir):
    with _mutex:
        return _key(job_id, files_dir) in _active

@contextmanager
def artifact_access(job_id, files_dir):
    key = _key(job_id, files_dir)
    with _mutex:
        lock = _locks.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ValueError('Conflict: job artifacts are busy. Please retry.')
    with _mutex:
        _active.add(key)
    try:
        yield
    finally:
        with _mutex:
            _active.discard(key)
        lock.release()

def guard_artifacts(func):
    import inspect
    signature = inspect.signature(func)
    @wraps(func)
    def guarded(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        directory = bound.arguments.get('files_dir', bound.arguments.get('output_base_dir', 'files'))
        with artifact_access(bound.arguments['job_id'], directory):
            return func(*args, **kwargs)
    return guarded
