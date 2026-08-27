"""GapEventFilesystemStorage — file-first atomic JSONL for DATA_INTEGRITY_GAP."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import List

from ...domain.gap_event import DataIntegrityGapEvent


def _atomic_append(path: Path, line: str) -> None:
    """Atomic append via tmp rewrite (file-first, ADR-002). For gap events we append JSONL atomically by rewriting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # read existing
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    new_content = existing + line + "\n"
    tmp = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex}"
    try:
        tmp.write_text(new_content, encoding="utf-8")
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


class GapEventFilesystemStorage:
    """Minimal persistence for DATA_INTEGRITY_GAP."""

    def __init__(self, base_path: Path | str = "data"):
        self.base = Path(base_path) / "events" / "data_integrity_gap"

    def _path(self, dataset_id: str, dataset_version: str) -> Path:
        return self.base / dataset_id / f"{dataset_version}.jsonl"

    def append(self, event: DataIntegrityGapEvent) -> Path:
        payload = event.payload
        ds = payload["dataset_id"]
        ver = payload["dataset_version"]
        path = self._path(ds, ver)
        line = json.dumps(event.to_dict(), sort_keys=True)
        _atomic_append(path, line)
        return path

    def list(self, dataset_id: str, dataset_version: str) -> List[DataIntegrityGapEvent]:
        path = self._path(dataset_id, dataset_version)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(DataIntegrityGapEvent.from_dict(json.loads(line)))
        return events

    def exists(self, dataset_id: str, dataset_version: str) -> bool:
        return self._path(dataset_id, dataset_version).exists()
