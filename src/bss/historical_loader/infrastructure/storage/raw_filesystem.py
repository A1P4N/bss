"""RawFilesystemStorage — file-first raw layer (ЧТЗ §5, ADR-002)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Iterable

from bss.domain.timeframe import Timeframe

from ...domain.dataset import CandleBatch
from ...domain.errors import CorruptChunkError, StorageError


def _atomic_write(path: Path, content: bytes) -> None:
    """Write content atomically via tmp + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex}"
    try:
        tmp.write_bytes(content)
        # fsync file
        with tmp.open("rb") as f:
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        tmp.replace(path)
        # fsync dir
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


class RawFilesystemStorage:
    """Filesystem implementation of RawStorage."""

    def __init__(self, base_path: Path | str = "data"):
        self.base = Path(base_path)

    def _chunk_path(self, source: str, symbol: str, timeframe: Timeframe, batch: CandleBatch) -> Path:
        start = batch.requested_range.start
        # path: data/raw/<source>/<symbol>/<timeframe>/<YYYY>/<MM>/<DD>/chunk-<start>-to-<end>.jsonl
        date_part = start.strftime("%Y/%m/%d")
        end = batch.requested_range.end
        # sanitize iso for filename
        def _san(s):
            return s.strftime("%Y%m%dT%H%M%S")
        fname = f"chunk-{_san(start)}-to-{_san(end)}.jsonl"
        return self.base / "raw" / source / symbol / timeframe.value / date_part / fname

    def _path_for_date(self, source: str, symbol: str, timeframe: Timeframe, date: str) -> Path:
        # date YYYY-MM-DD
        y, m, d = date.split("-")
        return self.base / "raw" / source / symbol / timeframe.value / y / m / d

    def write_raw(self, batch: CandleBatch) -> Path:
        path = self._chunk_path(batch.source, batch.symbol, batch.timeframe, batch)
        # serialize as JSONL of Candle dicts + header with requested_range
        lines = []
        # header line with requested_range for idempotency
        header = json.dumps({"requested_range": {"from": batch.requested_range.start.isoformat(), "to": batch.requested_range.end.isoformat()}, "source": batch.source, "symbol": batch.symbol, "timeframe": batch.timeframe.value})
        lines.append(header)
        for c in batch.candles:
            lines.append(json.dumps(c.to_dict()))
        content = "\n".join(lines).encode("utf-8") + b"\n" if lines else b""
        new_checksum = _checksum(content)

        if path.exists():
            existing = path.read_bytes()
            if _checksum(existing) == new_checksum:
                return path  # idempotent
            # different content — overwrite atomically (if not READY, allowed; here we just overwrite)
            # In raw layer, overwrite is allowed as re-download
        try:
            _atomic_write(path, content)
        except Exception as exc:
            raise StorageError(code="WRITE_FAILED", message=str(exc), context={"path": str(path)}) from exc
        return path

    def exists(self, source: str, symbol: str, timeframe: Timeframe, date: str) -> bool:
        p = self._path_for_date(source, symbol, timeframe, date)
        return p.exists() and any(p.iterdir())

    def list_raw(self, source: str, symbol: str, timeframe: Timeframe) -> list[Path]:
        base = self.base / "raw" / source / symbol / timeframe.value
        if not base.exists():
            return []
        result = sorted(base.rglob("*.jsonl"))
        return result

    def read_raw(self, source: str, symbol: str, timeframe: Timeframe, date: str) -> Iterable[CandleBatch]:
        dir_path = self._path_for_date(source, symbol, timeframe, date)
        if not dir_path.exists():
            return []
        # streaming generator
        def gen():
            from bss.domain.candle import Candle
            from bss.domain.time import parse_utc
            from bss.domain.time_range import TimeRange
            for f in sorted(dir_path.rglob("*.jsonl")):
                try:
                    text = f.read_text(encoding="utf-8")
                except Exception as exc:
                    raise CorruptChunkError(code="READ_FAILED", message=str(exc), context={"path": str(f)}) from exc
                lines = [l for l in text.splitlines() if l.strip()]
                if not lines:
                    continue
                try:
                    header = json.loads(lines[0])
                    rr = header.get("requested_range", {})
                    # fallback to date if header missing
                    if "from" in rr and "to" in rr:
                        requested_range = TimeRange(start=parse_utc(rr["from"]), end=parse_utc(rr["to"]))
                    else:
                        # reconstruct from filename? skip
                        continue
                    candles = []
                    for line in lines[1:]:
                        try:
                            d = json.loads(line)
                            candles.append(Candle.from_dict(d))
                        except Exception as exc:
                            raise CorruptChunkError(code="CORRUPT_CHUNK", message=str(exc), context={"path": str(f)}) from exc
                    yield CandleBatch(symbol=header.get("symbol", symbol), timeframe=Timeframe.from_string(header.get("timeframe", timeframe.value)), candles=tuple(candles), source=header.get("source", source), requested_range=requested_range)
                except CorruptChunkError:
                    raise
                except Exception as exc:
                    raise CorruptChunkError(code="CORRUPT_CHUNK", message=str(exc), context={"path": str(f)}) from exc
        return gen()

    def verify(self, source: str, symbol: str, timeframe: Timeframe) -> dict:
        """Simple verify for raw: check files exist and not corrupt (json parse)."""
        paths = self.list_raw(source, symbol, timeframe)
        corrupt = []
        for p in paths:
            try:
                text = p.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if line.strip():
                        json.loads(line)
            except Exception:
                corrupt.append(p)
        return {"total": len(paths), "corrupt": corrupt}
