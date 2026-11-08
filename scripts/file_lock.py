"""Same-process and cross-process lock for inbox and canonical state writes."""
import os
import threading
from contextlib import contextmanager
from pathlib import Path

_thread_lock = threading.RLock()
_depth = threading.local()


def _acquire_file(fh):
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        fh.write(b"\0")
        fh.flush()
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _release_file(fh):
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def state_lock(directory: Path):
    """Reentrant for the holding thread. Other threads and processes wait."""
    depth = getattr(_depth, "n", 0)
    if depth:
        _depth.n = depth + 1
        try:
            yield
        finally:
            _depth.n -= 1
        return
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".write.lock"
    fh = open(lock_path, "a+b")
    _thread_lock.acquire()
    try:
        _acquire_file(fh)
        _depth.n = 1
        try:
            yield
        finally:
            _depth.n = 0
            _release_file(fh)
    finally:
        _thread_lock.release()
        fh.close()
