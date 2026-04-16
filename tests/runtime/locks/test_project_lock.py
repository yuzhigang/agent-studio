import os
import pytest
import tempfile
from src.runtime.locks.project_lock import ProjectLock, LockAlreadyHeldError


def test_acquire_and_release_lock():
    with tempfile.TemporaryDirectory() as tmp:
        lock = ProjectLock(tmp)
        lock.acquire()
        assert os.path.exists(os.path.join(tmp, ".lock"))
        lock.release()
        assert not os.path.exists(os.path.join(tmp, ".lock"))


def test_second_acquire_raises():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        lock1 = ProjectLock(tmp)
        lock2 = ProjectLock(tmp)
        lock1.acquire()
        with pytest.raises(LockAlreadyHeldError):
            lock2.acquire()
        lock1.release()


def test_context_manager():
    with tempfile.TemporaryDirectory() as tmp:
        with ProjectLock(tmp) as lock:
            assert os.path.exists(os.path.join(tmp, ".lock"))
