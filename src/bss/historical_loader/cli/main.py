"""CLI thin adapter — historical_loader + replay."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import parse_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe


def _parse_time(s: str):
    return parse_utc(s)


def _make_services(base_path: Path, source=None):
    """Factory for DownloadService + Replay + Recovery with filesystem storages."""
    from bss.historical_loader.domain.normalization import CandleNormalizer
    from bss.historical_loader.domain.validation import CandleValidator
    from bss.historical_loader.infrastructure.networking.clock import SystemClock
    from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
    from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
    from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
    from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
    from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
    from bss.historical_loader.infrastructure.storage.gap_event_filesystem import GapEventFilesystemStorage
    from bss.historical_loader.infrastructure.storage.job_filesystem import JobFilesystemStorage
    from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
    from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
    from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage
    from bss.historical_loader.application.download_service import DownloadService
    from bss.historical_loader.application.recovery_service import RecoveryService
    from bss.replay.replay_data_source import ReplayDataSource

    # Use synthetic source if not provided (for E2E)
    if source is None:
        source = _synthetic_source()

    clock = SystemClock()
    rate = RateLimiter(rps=5, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)
    retry = RetryPolicy(max_attempts=5, initial_delay=0.1, max_delay=5.0, factor=2.0)

    raw = RawFilesystemStorage(base_path=base_path)
    norm = NormalizedFilesystemStorage(base_path=base_path)
    meta = MetadataFilesystemStorage(base_path=base_path)
    ckpt = CheckpointFilesystemStorage(base_path=base_path)
    job_store = JobFilesystemStorage(base_path=base_path)
    gap_store = GapEventFilesystemStorage(base_path=base_path)

    download_service = DownloadService(
        source=source,
        normalizer=CandleNormalizer(),
        validator=CandleValidator(),
        raw_storage=raw,
        normalized_storage=norm,
        metadata_storage=meta,
        checkpoint_storage=ckpt,
        job_storage=job_store,
        rate_limiter=rate,
        retry_policy=retry,
        clock=clock,
        gap_event_storage=gap_store,
    )
    replay_ds = ReplayDataSource(norm)
    recovery_service = RecoveryService(download_service=download_service)

    return download_service, replay_ds, recovery_service


def _synthetic_source():
    """Synthetic source for CLI E2E (generates deterministic candles)."""

    from bss.domain.candle import Candle
    from bss.domain.identifiers import CandleId
    from decimal import Decimal
    from datetime import timedelta

    class SyntheticSource:
        def available_range(self, symbol, timeframe):
            return TimeRange(start=parse_utc("2025-01-01T00:00:00Z"), end=parse_utc("2025-12-31T00:00:00Z"))

        def download(self, symbol, timeframe, start, end):
            from bss.historical_loader.domain.dataset import CandleBatch

            rr = TimeRange(start=start, end=end)
            candles = []
            cur = start
            interval = timedelta(minutes=timeframe.duration_minutes())
            while cur < end:
                candles.append(
                    Candle(
                        candle_id=CandleId(f"cnd_{symbol}_{timeframe.value}_{cur.isoformat()}"),
                        instrument_id=f"inst_{symbol.lower()}",
                        symbol=symbol,
                        timeframe=timeframe,
                        open_time=cur,
                        close_time=cur + interval,
                        open=Decimal("100"),
                        high=Decimal("101"),
                        low=Decimal("99"),
                        close=Decimal("100"),
                        volume=Decimal("1000"),
                    )
                )
                cur += interval
            return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="synthetic", requested_range=rr)

    return SyntheticSource()


def _error_exit(msg: str, code: int = 1):
    sys.stderr.write(json.dumps({"error": msg}) + "\n")
    sys.exit(code)


def cmd_download(args):
    try:
        base = Path(args.base_path or "data")
        ds_id = DatasetId(args.dataset_id)
        ver = DatasetVersion(args.version)
        symbol = args.symbol
        tf = Timeframe.from_string(args.timeframe)
        start = parse_utc(args.from_time)
        end = parse_utc(args.to_time)
        rr = TimeRange(start=start, end=end)
        now = datetime.now(timezone.utc)
        download_service, _, _ = _make_services(base)
        job = download_service.create_job(ds_id, ver, "synthetic", symbol, tf, rr, now=now)
        result = download_service.run(job.job_id, now=datetime.now(timezone.utc))
        sys.stdout.write(json.dumps({"job_id": result.job_id, "status": result.status.value, "dataset_id": str(ds_id), "version": str(ver)}) + "\n")
        sys.exit(0)
    except Exception as e:
        _error_exit(str(e), 1)


def cmd_resume(args):
    try:
        base = Path(args.base_path or "data")
        download_service, _, _ = _make_services(base)
        job = download_service.job_storage.load(args.job_id)
        if job is None:
            _error_exit(f"job {args.job_id} not found", 2)
        result = download_service.run(args.job_id, now=datetime.now(timezone.utc))
        sys.stdout.write(json.dumps({"job_id": result.job_id, "status": result.status.value}) + "\n")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        _error_exit(str(e), 1)


def cmd_recover(args):
    try:
        base = Path(args.base_path or "data")
        download_service, _, recovery_service = _make_services(base)
        ds_id = DatasetId(args.dataset_id)
        ver = DatasetVersion(args.version)
        plan = recovery_service.recover(ds_id, ver, now=datetime.now(timezone.utc))
        sys.stdout.write(json.dumps({"dataset_id": str(ds_id), "version": str(ver), "recovered_ranges": len(plan.ranges), "is_empty": plan.is_empty}) + "\n")
        sys.exit(0)
    except Exception as e:
        _error_exit(str(e), 1)


def cmd_replay(args):
    try:
        base = Path(args.base_path or "data")
        _, replay_ds, _ = _make_services(base)
        ds_id = DatasetId(args.dataset_id)
        ver = DatasetVersion(args.version)
        symbol = args.symbol
        tf = Timeframe.from_string(args.timeframe)
        start = parse_utc(args.from_time)
        end = parse_utc(args.to_time)
        rr = TimeRange(start=start, end=end)
        # run_id optional
        run_id = args.run_id or None
        count = 0
        for event in replay_ds.replay(ds_id, ver, symbol, tf, rr, run_id=run_id):
            sys.stdout.write(json.dumps(event.to_dict()) + "\n")
            count += 1
            if args.limit and count >= int(args.limit):
                break
        sys.stderr.write(json.dumps({"replayed": count}) + "\n")
        sys.exit(0)
    except Exception as e:
        _error_exit(str(e), 1)


def build_parser():
    parser = argparse.ArgumentParser(prog="loader")
    parser.add_argument("--base-path", dest="base_path", default=None, help="base data path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download", help="download dataset")
    p_dl.add_argument("--dataset-id", required=True, dest="dataset_id")
    p_dl.add_argument("--version", required=True, dest="version")
    p_dl.add_argument("--symbol", required=True)
    p_dl.add_argument("--timeframe", required=True)
    p_dl.add_argument("--from", required=True, dest="from_time")
    p_dl.add_argument("--to", required=True, dest="to_time")
    p_dl.set_defaults(func=cmd_download)

    p_res = sub.add_parser("resume", help="resume job")
    p_res.add_argument("--job-id", required=True, dest="job_id")
    p_res.set_defaults(func=cmd_resume)

    p_rec = sub.add_parser("recover", help="recover dataset")
    p_rec.add_argument("--dataset-id", required=True, dest="dataset_id")
    p_rec.add_argument("--version", required=True, dest="version")
    p_rec.set_defaults(func=cmd_recover)

    p_rep = sub.add_parser("replay", help="replay dataset")
    p_rep.add_argument("--dataset-id", required=True, dest="dataset_id")
    p_rep.add_argument("--version", required=True, dest="version")
    p_rep.add_argument("--symbol", required=True)
    p_rep.add_argument("--timeframe", required=True)
    p_rep.add_argument("--from", required=True, dest="from_time")
    p_rep.add_argument("--to", required=True, dest="to_time")
    p_rep.add_argument("--run-id", required=False, dest="run_id", default=None)
    p_rep.add_argument("--limit", required=False, default=None)
    p_rep.set_defaults(func=cmd_replay)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # thin: no business logic here
    args.func(args)


if __name__ == "__main__":
    main()
