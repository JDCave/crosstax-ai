"""Nonblocking single-host job lock (POSIX flock / Windows msvcrt)."""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def job_lock(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise OSError(f"Refusing to lock symlink: {path}")
    flags = os.O_CREAT | os.O_RDWR
    if sys.platform != "win32":
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    acquired = False
    try:
        acquired = _try_lock(descriptor)
        yield acquired
    finally:
        if acquired:
            _unlock(descriptor)
        os.close(descriptor)
        # Do not unlink: replacing an inode while another process waits breaks exclusivity.


def _try_lock(descriptor: int) -> bool:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    else:
        import fcntl

        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


def _unlock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
