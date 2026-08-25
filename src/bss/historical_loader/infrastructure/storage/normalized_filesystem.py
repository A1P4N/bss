"""NormalizedFilesystemStorage — file-first normalized layer (ЧТЗ §6, ADR-002)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Iterable

from bss.domain.candle import Candle
from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.timeframe import Timeframe

from ...domain.dataset import CandleBatch
from ...domain.errors import CorruptChunkError, StorageError


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


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NormalizedFilesystemStorage:
    """Filesystem normalized storage (DatasetStorage)."""

    def __init__(self, base_path: Path | str = "data"):
        self.base = Path(base_path)

    def _chunk_path(self, dataset_id: DatasetId, version: DatasetVersion, batch: CandleBatch) -> Path:
        start = batch.requested_range.start
        end = batch.requested_range.end
        date_part = start.strftime("%Y/%m/%d")
        def _san(s):
            return s.strftime("%Y%m%dT%H%M%S")
        fname = f"chunk-{_san(start)}-to-{_san(end)}.jsonl"
        return self.base / "normalized" / str(dataset_id) / str(version) / batch.symbol / batch.timeframe.value / date_part / fname

    def write_batch(self, batch: CandleBatch, dataset_id: DatasetId, version: DatasetVersion) -> Path:
        path = self._chunk_path(dataset_id, version, batch)
        # serialize as JSONL: header + candles
        import json as _json

        header = _json.dumps({"symbol": batch.symbol, "timeframe": batch.timeframe.value, "requested_range": {"from": batch.requested_range.start.isoformat(), "to": batch.requested_range.end.isoformat()}, "source": batch.source})
        lines = [header] + [_json.dumps(c.to_dict()) for c in batch.candles]
        content = "\n".join(lines).encode("utf-8") + b"\n" if lines else b""
        new_cs = _checksum(content)
        if path.exists():
            existing = path.read_bytes()
            if _checksum(existing) == new_cs:
                return path  # idempotent
            # different content — for MVP, overwrite atomically (if READY immutability is enforced at metadata layer)
        try:
            _atomic_write(path, content)
        except Exception as exc:
            raise StorageError(code="WRITE_FAILED", message=str(exc), context={"path": str(path)}) from exc
        return path

    def list_chunks(self, dataset_id: DatasetId, version: DatasetVersion) -> list[Path]:
        base = self.base / "normalized" / str(dataset_id) / str(version)
        if not base.exists():
            return []
        return sorted(base.rglob("*.jsonl"))

    def stream(self, dataset_id: DatasetId, version: DatasetVersion, symbol: str, timeframe: Timeframe, start=None, end=None) -> Iterable[Candle]:
        """Streaming read — yields candles sorted by open_time, filtered by [start,end) if given."""
        base = self.base / "normalized" / str(dataset_id) / str(version) / symbol / timeframe.value
        if not base.exists():
            return
            yield  # make generator

        # collect all chunk files sorted
        files = sorted(base.rglob("*.jsonl"))
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as exc:
                raise CorruptChunkError(code="READ_FAILED", message=str(exc), context={"path": str(f)}) from exc
            lines = [l for l in text.splitlines() if l.strip()]
            if not lines:
                continue
            # validate header
            try:
                json.loads(lines[0])
            except Exception as exc:
                raise CorruptChunkError(code="CORRUPT_CHUNK", message=f"corrupt header: {exc}", context={"path": str(f)}) from exc
            # skip header line
            for line in lines[1:]:
                # header is lines[0], contains requested_range
                try:
                    d = json.loads(line)
                    c = Candle.from_dict(d)
                except Exception as exc:
                    raise CorruptChunkError(code="CORRUPT_CHUNK", message=str(exc), context={"path": str(f)}) from exc
                if start is not None and c.open_time < start:
                    continue
                if end is not None and c.open_time >= end:
                    continue
                yield c

    def verify(self, dataset_id: DatasetId, version: DatasetVersion):
        from ...domain.interfaces.dataset_storage import ChecksumReport as Report

        paths = self.list_chunks(dataset_id, version)
        corrupt = []
        for p in paths:
            try:
                text = p.read_text(encoding="utf-8")
                # check each line is valid json
                for line in text.splitlines():
                    if line.strip():
                        json.loads(line)
            except Exception:
                corrupt.append(p)
        missing: list[Path] = []  # not tracking expected vs actual here — gap detector does
        ok = len(corrupt) == 0
        return Report(ok=ok, missing=missing, corrupt=corrupt)
