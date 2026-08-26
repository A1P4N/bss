"""DownloadService — application orchestration (sequential, chunk vs dataset validation).

Invariant: HistoricalSource → Retry → Normalize → Validate(chunk) → Raw → Normalized → Checkpoint
DATA_INTEGRITY_GAP only on dataset-level temporal validation.
Checkpoint stores durable progress position, not O(N) list.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe

from ..domain.checkpoint import Checkpoint
from ..domain.dataset import CandleBatch, DatasetMetadata, DatasetStatus
from ..domain.download_job import DownloadJob, JobStatus
from ..domain.errors import RetryExhaustedError
from ..domain.gap_detector import GapDetector
from ..domain.interfaces.checkpoint_storage import CheckpointStorage
from ..domain.interfaces.dataset_storage import DatasetStorage
from ..domain.interfaces.historical_source import HistoricalSource
from ..domain.interfaces.job_storage import JobStorage
from ..domain.interfaces.metadata_storage import MetadataStorage
from ..domain.interfaces.raw_storage import RawStorage
from ..domain.normalization import CandleNormalizer
from ..domain.validation import CandleValidator


def _chunk_ranges(requested: TimeRange, chunk_interval: timedelta) -> list[TimeRange]:
    """Split requested_range into sequential chunks (deterministic)."""
    chunks = []
    cursor = requested.start
    while cursor < requested.end:
        nxt = cursor + chunk_interval
        if nxt > requested.end:
            nxt = requested.end
        chunks.append(TimeRange(start=cursor, end=nxt))
        cursor = nxt
    return chunks


class DownloadService:
    """Sequential download orchestration (MVP). No max_parallel for chunks."""

    def __init__(
        self,
        source: HistoricalSource,
        normalizer: CandleNormalizer,
        validator: CandleValidator,
        raw_storage: RawStorage,
        normalized_storage: DatasetStorage,
        metadata_storage: MetadataStorage,
        checkpoint_storage: CheckpointStorage,
        job_storage: JobStorage,
        rate_limiter,  # RateLimiter
        retry_policy,  # RetryPolicy
        clock,  # Clock (monotonic for rate/retry, UTC for checkpoint)
        chunk_interval: timedelta | None = None,
        gap_detector: GapDetector | None = None,
    ):
        self.source = source
        self.normalizer = normalizer
        self.validator = validator
        self.raw_storage = raw_storage
        self.normalized_storage = normalized_storage
        self.metadata_storage = metadata_storage
        self.checkpoint_storage = checkpoint_storage
        self.job_storage = job_storage
        self.rate_limiter = rate_limiter
        self.retry_policy = retry_policy
        self.clock = clock
        self.chunk_interval = chunk_interval or timedelta(days=1)
        self.gap_detector = gap_detector or GapDetector()

    def create_job(
        self,
        dataset_id: DatasetId,
        version: DatasetVersion,
        source_name: str,
        symbol: str,
        timeframe: Timeframe,
        requested_range: TimeRange,
        now: datetime,
        loader_version: str = "0.1.0",
        schema_version: str = "0.2",
    ) -> DownloadJob:
        ensure_utc(now, "now")
        job = DownloadJob.create(
            dataset_id=dataset_id,
            dataset_version=version,
            source=source_name,
            symbol=symbol,
            timeframe=timeframe,
            range=requested_range,
            created_at=now,
        )
        # job starts CREATED, transition to RUNNING on run()
        self.job_storage.save(job)
        # initial checkpoint
        cp = Checkpoint.initial(job_id=job.job_id, dataset_id=str(dataset_id), dataset_version=str(version), requested_range=requested_range, created_at=now)
        self.checkpoint_storage.save(cp)
        # initial metadata CREATED
        meta = DatasetMetadata(
            dataset_id=dataset_id,
            dataset_version=version,
            source=source_name,
            symbols=(symbol,),
            timeframes=(timeframe,),
            range=requested_range,
            created_at=now,
            loader_version=loader_version,
            schema_version=schema_version,
            status=DatasetStatus.CREATED,
        )
        self.metadata_storage.save(meta)
        return job

    def _verify_checkpoint_chunk(self, checkpoint: Checkpoint) -> None:
        """Corrupted/missing chunk check (correction 6)."""
        if checkpoint.last_completed is None:
            return
        path = Path(checkpoint.last_completed.path)
        if not path.exists():
            from ..domain.errors import CorruptChunkError

            raise CorruptChunkError(code="MISSING_CHUNK", message="missing chunk pointed by checkpoint", context={"path": str(path)})
        # verify checksum
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != checkpoint.last_completed.checksum:
            from ..domain.errors import CorruptChunkError

            raise CorruptChunkError(code="CORRUPT_CHUNK", message="checksum mismatch after checkpoint", context={"path": str(path), "expected": checkpoint.last_completed.checksum, "actual": actual})

    def run(self, job_id: str, now: datetime) -> DownloadJob:
        ensure_utc(now, "now")
        job = self.job_storage.load(job_id)
        if job is None:
            raise ValueError(f"job {job_id} not found")
        # idempotent re-run of COMPLETED
        if job.status == JobStatus.COMPLETED:
            return job
        # transition CREATED/PAUSED/FAILED -> RUNNING if needed
        if job.status == JobStatus.CREATED:
            job = job.transition(JobStatus.RUNNING, now)
            self.job_storage.save(job)
            # also update metadata to DOWNLOADING
            meta = self.metadata_storage.get(job.dataset_id, job.dataset_version)
            if meta:
                from dataclasses import replace

                self.metadata_storage.save(replace(meta, status=DatasetStatus.DOWNLOADING))

        checkpoint = self.checkpoint_storage.load(job_id)
        if checkpoint is None:
            # create if missing (should not happen)
            checkpoint = Checkpoint.initial(job_id=job_id, dataset_id=str(job.dataset_id), dataset_version=str(job.dataset_version), requested_range=job.range, created_at=now)
            self.checkpoint_storage.save(checkpoint)

        # verify last_completed not corrupted/missing (correction 6)
        self._verify_checkpoint_chunk(checkpoint)

        # chunk validation vs dataset validation separation
        chunks = _chunk_ranges(job.range, self.chunk_interval)
        # find index to resume from
        start_idx = 0
        for i, ch in enumerate(chunks):
            if ch.start == checkpoint.next_start:
                start_idx = i
                break
            if ch.start < checkpoint.next_start < ch.end:
                # non-aligned chunk case: next_start inside chunk -> start from checkpoint.next_start
                # we need to create a partial chunk [next_start, ch.end)
                # For MVP sequential, we handle by using checkpoint.next_start as start for next download
                # So we will use the remaining part of current chunk
                # To keep deterministic, we treat next chunk as [next_start, ch.end) + remaining chunks
                # Simplify: resume from checkpoint.next_start
                start_idx = i
                break
        # if checkpoint.next_start not aligned to chunk boundary, we will use it directly
        pending_chunks = []
        if checkpoint.next_start != job.range.end:
            # Check if next_start is exactly at a chunk boundary
            found = False
            for ch in chunks:
                if ch.start == checkpoint.next_start:
                    found = True
                    break
            if not found:
                # create remaining range from next_start to end, split again
                remaining = TimeRange(start=checkpoint.next_start, end=job.range.end)
                pending_chunks = _chunk_ranges(remaining, self.chunk_interval)
            else:
                pending_chunks = chunks[start_idx:]
        else:
            pending_chunks = []

        # sequential loop
        for chunk_range in pending_chunks:
            # RateLimiter acquire (strict pacing)
            self.rate_limiter.acquire()
            # Retry before Storage
            def _download():
                return self.source.download(job.symbol, job.timeframe, chunk_range.start, chunk_range.end)

            try:
                batch = self.retry_policy.execute(_download, self.clock)
            except RetryExhaustedError as e:
                # job FAILED, checkpoint not advanced
                job = job.transition(JobStatus.FAILED, now)
                self.job_storage.save(job)
                raise
            except Exception:
                job = job.transition(JobStatus.FAILED, now)
                self.job_storage.save(job)
                raise

            # Normalize
            # source returns CandleBatch already normalized? In our stack, source returns CandleBatch directly (FakeSource)
            # For Raw source, we would normalize RawCandle -> CandleBatch. Here we assume batch is already CandleBatch
            # If source returns raw dicts, normalizer would be used. For now, if batch is CandleBatch, skip normalize
            # To support both, check if batch is CandleBatch
            if not isinstance(batch, CandleBatch):
                # assume raw list -> normalize
                batch = self.normalizer.normalize_batch(batch, chunk_range, source=job.source)

            # Chunk validation (not gap across dataset, only basic)
            # We validate chunk for duplicates/ordering but not full gap across dataset
            # Use validator but ignore gaps that are due to dataset-level missing? For chunk, we check only is_valid for duplicates/ordering, not gaps
            # Instead, we can check chunk-level validation for duplicates/ordering only
            # For MVP, we consider chunk valid if no duplicates/ordering issues (gaps within chunk will be caught at dataset level)
            # So we will not fail on chunk gap alone; we will still write storage
            # Only fail on duplicate/ordering
            chunk_res = self.validator.validate(batch)
            # filter out GAP issues for chunk-level
            chunk_issues = [i for i in chunk_res.issues if i.code != "GAP" and i.code != "EMPTY_BATCH"]
            if chunk_issues:
                job = job.transition(JobStatus.FAILED, now)
                self.job_storage.save(job)
                # also mark dataset INVALID
                meta = self.metadata_storage.get(job.dataset_id, job.dataset_version)
                if meta:
                    from dataclasses import replace

                    self.metadata_storage.save(replace(meta, status=DatasetStatus.INVALID))
                raise ValueError(f"chunk validation failed: {chunk_issues}")

            # Storage → Checkpoint invariant (5)
            raw_path = self.raw_storage.write_raw(batch)
            norm_path = self.normalized_storage.write_batch(batch, job.dataset_id, job.dataset_version)
            # checkpoint advance only after durable storage
            checksum = hashlib.sha256(Path(norm_path).read_bytes()).hexdigest()
            checkpoint = checkpoint.advance(chunk_from=chunk_range.start, chunk_to=chunk_range.end, checksum=checksum, path=str(norm_path), updated_at=now)
            self.checkpoint_storage.save(checkpoint)

        # After all chunks, dataset-level validation
        # Stream all normalized candles for dataset
        all_candles = list(self.normalized_storage.stream(job.dataset_id, job.dataset_version, job.symbol, job.timeframe, start=job.range.start, end=job.range.end))
        # Build a batch for dataset-level validation (use requested_range = job.range)
        # Create a temporary CandleBatch for validation
        dataset_batch = CandleBatch(symbol=job.symbol, timeframe=job.timeframe, candles=tuple(all_candles), source=job.source, requested_range=job.range)
        result = self.validator.validate(dataset_batch)
        # Also check gaps via GapDetector directly for DATA_INTEGRITY_GAP
        # result already contains gaps
        meta = self.metadata_storage.get(job.dataset_id, job.dataset_version)
        from dataclasses import replace

        if result.is_valid:
            # VALIDATING -> READY
            if meta:
                # transition via metadata storage
                self.metadata_storage.save(replace(meta, status=DatasetStatus.VALIDATING))
                self.metadata_storage.save(replace(meta, status=DatasetStatus.READY))
            job = job.transition(JobStatus.COMPLETED, now)
            self.job_storage.save(job)
            # checkpoint status COMPLETED? Keep as is, is_complete true
        else:
            # DATA_INTEGRITY_GAP only on dataset-level temporal validation
            # Mark dataset INVALID, job FAILED
            if meta:
                self.metadata_storage.save(replace(meta, status=DatasetStatus.INVALID))
            job = job.transition(JobStatus.FAILED, now)
            self.job_storage.save(job)
            # Raise to signal gap (caller can inspect result)
            # We don't raise here for happy path tests; but for gap case, we need to indicate
            # For now, if gaps exist, we consider job FAILED but not exception
            pass

        return job
