"""JobFilesystemStorage — atomic JSON for DownloadJob."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from ...domain.download_job import DownloadJob
from ...domain.errors import StorageError


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex}"
    try:
        tmp.write_bytes(content)
        with tmp.open("rb") as f:
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        tmp.replace(path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class JobFilesystemStorage:
    def __init__(self, base_path: Path | str = "data"):
        self.base = Path(base_path) / "jobs"

    def _path(self, job_id: str) -> Path:
        return self.base / f"{job_id}.json"

    def save(self, job: DownloadJob) -> None:
        path = self._path(job.job_id)
        content = json.dumps(job.to_dict(), indent=2, sort_keys=True).encode("utf-8")
        try:
            _atomic_write(path, content)
        except Exception as exc:
            raise StorageError(code="WRITE_FAILED", message=str(exc), context={"path": str(path)}) from exc

    def load(self, job_id: str) -> DownloadJob | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DownloadJob.from_dict(data)
        except Exception as exc:
            raise StorageError(code="CORRUPT_JOB", message=str(exc), context={"path": str(path)}) from exc

    def exists(self, job_id: str) -> bool:
        return self._path(job_id).exists()
