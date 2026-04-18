import os
import json
import fasteners


class LockAlreadyHeldError(RuntimeError):
    pass


class WorldLock:
    def __init__(self, world_dir: str):
        self._world_dir = world_dir
        self._meta_path = os.path.join(world_dir, ".lock")
        self._lockfile_path = os.path.join(world_dir, ".lockfile")
        self._lock = None
        self._acquired = False

    def acquire(self) -> None:
        os.makedirs(self._world_dir, exist_ok=True)
        self._lock = fasteners.InterProcessLock(self._lockfile_path)
        got_it = self._lock.acquire(blocking=False)
        if not got_it:
            pid = None
            if os.path.exists(self._meta_path):
                try:
                    with open(self._meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        pid = data.get("pid")
                except Exception:
                    pass
            world_id = os.path.basename(self._world_dir)
            if pid is not None:
                raise LockAlreadyHeldError(
                    f"World {world_id} is already loaded in process {pid}"
                )
            raise LockAlreadyHeldError(f"World {world_id} is already locked")
        self._acquired = True
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"pid": os.getpid(), "started_at": _now_iso()}, f
            )

    def release(self) -> None:
        if self._acquired and self._lock is not None:
            try:
                if os.path.exists(self._meta_path):
                    os.remove(self._meta_path)
            except OSError:
                pass
            self._lock.release()
            self._acquired = False
            self._lock = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
