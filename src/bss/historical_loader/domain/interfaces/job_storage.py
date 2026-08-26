"""JobStorage — domain interface for DownloadJob persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..download_job import DownloadJob


@runtime_checkable
class JobStorage(Protocol):
    def save(self, job: DownloadJob) -> None: ...
    def load(self, job_id: str) -> DownloadJob | None: ...
    def exists(self, job_id: str) -> bool: ...
