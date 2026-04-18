import os
import pytest
import tempfile
from src.runtime.locks.world_lock import WorldLock, LockAlreadyHeldError


def test_acquire_and_release_lock():
    with tempfile.TemporaryDirectory() as tmp:
        lock = WorldLock(tmp)
        lock.acquire()
        assert os.path.exists(os.path.join(tmp, ".lock"))
        lock.release()
        assert not os.path.exists(os.path.join(tmp, ".lock"))


def test_second_acquire_raises():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        lock1 = WorldLock(tmp)
        lock2 = WorldLock(tmp)
        lock1.acquire()
        with pytest.raises(LockAlreadyHeldError):
            lock2.acquire()
        lock1.release()


def test_context_manager():
    with tempfile.TemporaryDirectory() as tmp:
        with WorldLock(tmp) as lock:
            assert os.path.exists(os.path.join(tmp, ".lock"))
