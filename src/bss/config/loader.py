"""Config loader — YAML defaults + BSS_* env override (domain-free)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # fallback to simple parser


@dataclass(frozen=True)
class AppConfig:
    base_path: str
    source_name: str
    source_base_url: str
    source_timeout: float
    rate_limit_rps: float
    rate_limit_max_parallel: int
    retry_max_attempts: int
    retry_initial_delay: float
    retry_max_delay: float
    retry_backoff_factor: float
    chunk_interval: timedelta
    loader_version: str
    schema_version: str


def _parse_interval(s: str) -> timedelta:
    s = s.strip().lower()
    if s.endswith("d"):
        return timedelta(days=float(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=float(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=float(s[:-1]))
    raise ValueError(f"invalid interval {s!r}, expected e.g. 1d, 12h, 30m")


def _get_env(key: str, default: Any = None) -> Any:
    return os.environ.get(key, default)


def load_config(config_path: Path | str | None = None) -> AppConfig:
    # default path
    if config_path is None:
        # try config/default.yaml relative to project root
        candidate = Path(__file__).resolve().parents[3] / "config" / "default.yaml"
        if candidate.exists():
            config_path = candidate
        else:
            # fallback to src/../config
            candidate2 = Path("config/default.yaml")
            if candidate2.exists():
                config_path = candidate2
            else:
                config_path = None

    data: Dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        if yaml:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            # very simple fallback: parse only needed keys via manual read
            # For MVP, require yaml
            raise ImportError("pyyaml required to load config")

    # helpers to get nested with env override
    def _get(path: str, default):
        cur = data
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        return cur if cur is not None else default

    base_path = _get_env("BSS_STORAGE_BASE_PATH", _get("storage.base_path", "data"))
    source_name = _get_env("BSS_SOURCE_NAME", _get("source.name", "binance"))
    source_base_url = _get_env("BSS_SOURCE_BASE_URL", _get("source.base_url", "https://api.binance.com"))
    source_timeout = float(_get_env("BSS_SOURCE_TIMEOUT", str(_get("source.timeout_seconds", 10.0))))
    rps = float(_get_env("BSS_RATE_LIMIT_RPS", str(_get("source.rate_limit.requests_per_second", 5))))
    max_parallel = int(_get_env("BSS_RATE_LIMIT_MAX_PARALLEL", str(_get("source.rate_limit.max_parallel_requests", 4))))
    max_attempts = int(_get_env("BSS_RETRY_MAX_ATTEMPTS", str(_get("source.retry.max_attempts", 5))))
    initial_delay = float(_get_env("BSS_RETRY_INITIAL_DELAY", str(_get("source.retry.initial_delay_seconds", 1.0))))
    max_delay = float(_get_env("BSS_RETRY_MAX_DELAY", str(_get("source.retry.max_delay_seconds", 60.0))))
    backoff_factor = float(_get_env("BSS_RETRY_BACKOFF_FACTOR", str(_get("source.retry.backoff_factor", 2.0))))
    chunk_interval_str = _get_env("BSS_LOADER_CHUNK_INTERVAL", _get("loader.chunk_interval", "1d"))
    chunk_interval = _parse_interval(str(chunk_interval_str))
    loader_version = str(_get("dataset.loader_version", "0.1.0"))
    schema_version = str(_get("dataset.schema_version", "0.2"))

    return AppConfig(
        base_path=base_path,
        source_name=source_name,
        source_base_url=source_base_url,
        source_timeout=source_timeout,
        rate_limit_rps=rps,
        rate_limit_max_parallel=max_parallel,
        retry_max_attempts=max_attempts,
        retry_initial_delay=initial_delay,
        retry_max_delay=max_delay,
        retry_backoff_factor=backoff_factor,
        chunk_interval=chunk_interval,
        loader_version=loader_version,
        schema_version=schema_version,
    )
