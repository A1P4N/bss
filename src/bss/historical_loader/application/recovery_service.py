"""RecoveryService — stateless, uses DownloadService (no second pipeline)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from bss.domain.identifiers import DatasetId, DatasetVersion

from ..domain.gap_detector import GapDetector
from ..domain.recovery import RecoveryPlan, RecoveryRange, RecoveryReason
from ..domain.validation import CandleValidator


class RecoveryService:
    """Builds deterministic RecoveryPlan and recovers via DownloadService."""

    def __init__(
        self,
        download_service,  # DownloadService
        gap_detector: GapDetector | None = None,
        validator: CandleValidator | None = None,
    ):
        self.download_service = download_service
        self.gap_detector = gap_detector or GapDetector()
        self.validator = validator or CandleValidator()

    def build_plan(self, dataset_id: DatasetId, version: DatasetVersion) -> RecoveryPlan:
        meta = self.download_service.metadata_storage.get(dataset_id, version)
        if meta is None:
            raise ValueError(f"dataset {dataset_id} {version} not found")

        # Check for missing/corrupt chunks via checkpoint
        ranges: List[RecoveryRange] = []

        # Find checkpoint for this dataset/version (search jobs)
        # For MVP, we find any job for this dataset/version
        # If multiple jobs, use latest checkpoint
        # Instead, we directly use GapDetector on normalized storage stream
        # Stream all candles for dataset
        job = None
        # find job by scanning job storage? For MVP, we assume one job per dataset
        # Instead, use metadata range
        # First check for corrupt chunks via verify (before streaming which may raise)
        report = self.download_service.normalized_storage.verify(dataset_id, version)
        for corrupt_path in report.corrupt:
            # For corrupt, try to infer range from file header, fallback to whole dataset
            try:
                import json

                text = corrupt_path.read_text(encoding="utf-8")
                header = json.loads(text.splitlines()[0]) if text and text.splitlines()[0].strip().startswith("{") else {}
                rr = header.get("requested_range") or {}
                from bss.domain.time import parse_utc

                if "from" in rr and "to" in rr:
                    c_from = parse_utc(rr["from"])
                    c_to = parse_utc(rr["to"])
                    ranges.append(RecoveryRange(start=c_from, end=c_to, reason=RecoveryReason.CORRUPT_CHUNK))
                    continue
            except Exception:
                pass
            ranges.append(RecoveryRange(start=meta.range.start, end=meta.range.end, reason=RecoveryReason.CORRUPT_CHUNK))

        # Try gap detection via stream — handle corrupt stream gracefully
        try:
            all_candles = list(
                self.download_service.normalized_storage.stream(
                    dataset_id, version, meta.symbols[0], meta.timeframes[0], start=meta.range.start, end=meta.range.end
                )
            )
            all_candles = sorted(all_candles, key=lambda c: c.open_time)
            from ..domain.dataset import CandleBatch

            batch = CandleBatch(
                symbol=meta.symbols[0],
                timeframe=meta.timeframes[0],
                candles=tuple(all_candles),
                source=meta.source,
                requested_range=meta.range,
            )
            gaps = self.gap_detector.find_gaps(batch)
            for gap in gaps:
                ranges.append(
                    RecoveryRange(start=gap.missing_from, end=gap.missing_to, reason=RecoveryReason.DATA_INTEGRITY_GAP)
                )
        except Exception as exc:
            from ..domain.errors import CorruptChunkError

            if isinstance(exc, CorruptChunkError):
                # already handled via report.corrupt, but ensure at least one range
                if not any(r.reason == RecoveryReason.CORRUPT_CHUNK for r in ranges):
                    ranges.append(RecoveryRange(start=meta.range.start, end=meta.range.end, reason=RecoveryReason.CORRUPT_CHUNK))
            else:
                raise
            # For corrupt, we need to infer its time range from filename or header
            # For MVP, treat corrupt as gap covering its expected range
            # Try to read header
            try:
                import json

                text = corrupt_path.read_text(encoding="utf-8")
                header = json.loads(text.splitlines()[0]) if text else {}
                rr = header.get("requested_range") or header.get("range") or {}
                # Try to parse
                from bss.domain.time import parse_utc

                if "from" in rr and "to" in rr:
                    c_from = parse_utc(rr["from"])
                    c_to = parse_utc(rr["to"])
                    ranges.append(RecoveryRange(start=c_from, end=c_to, reason=RecoveryReason.CORRUPT_CHUNK))
            except Exception:
                # fallback: use whole dataset range
                ranges.append(RecoveryRange(start=meta.range.start, end=meta.range.end, reason=RecoveryReason.CORRUPT_CHUNK))

        # Missing chunk: if checkpoint last_completed path missing
        # Find any checkpoint for this dataset
        # We scan checkpoint storage for jobs matching dataset_id/version
        # For MVP, we check if any gap already covers, else add missing
        # To keep deterministic, sort and dedup
        # Deduplicate and sort
        # Sort by start
        ranges = sorted(ranges, key=lambda r: r.start)
        # Merge overlapping? For now keep as is, but ensure not overlapping (gap detector already non-overlapping)
        # Deduplicate same start/end
        seen = set()
        deduped = []
        for r in ranges:
            key = (r.start.isoformat(), r.end.isoformat())
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        deduped = sorted(deduped, key=lambda r: r.start)

        return RecoveryPlan(dataset_id=dataset_id, dataset_version=version, ranges=tuple(deduped))

    def recover(self, dataset_id: DatasetId, version: DatasetVersion, now: datetime) -> RecoveryPlan:
        from bss.domain.time import ensure_utc

        ensure_utc(now, "now")
        meta = self.download_service.metadata_storage.get(dataset_id, version)
        if meta is None:
            raise ValueError("dataset not found")

        plan = self.build_plan(dataset_id, version)
        if plan.is_empty:
            return plan

        # For each recovery range, use DownloadService to re-download
        # Use the symbol/timeframe from metadata (first)
        symbol = meta.symbols[0]
        timeframe = meta.timeframes[0]
        for rec_range in plan.ranges:
            # Use DownloadService.download_range (sequential, no new job)
            # This will retry, normalize, validate chunk, write storage
            self.download_service.download_range(
                dataset_id=dataset_id,
                version=version,
                symbol=symbol,
                timeframe=timeframe,
                start=rec_range.start,
                end=rec_range.end,
                now=now,
            )

        # After all ranges, re-validate whole dataset
        all_candles = list(
            self.download_service.normalized_storage.stream(dataset_id, version, symbol, timeframe, start=meta.range.start, end=meta.range.end)
        )
        all_candles = sorted(all_candles, key=lambda c: c.open_time)
        from ..domain.dataset import CandleBatch, DatasetStatus
        from dataclasses import replace

        batch = CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(all_candles), source=meta.source, requested_range=meta.range)
        result = self.validator.validate(batch)

        cur = self.download_service.metadata_storage.get(dataset_id, version)
        if result.is_valid:
            # VALIDATING -> READY (only after full validation)
            self.download_service.metadata_storage.save(replace(cur, status=DatasetStatus.READY))
        else:
            self.download_service.metadata_storage.save(replace(cur, status=DatasetStatus.INVALID))

        return plan
