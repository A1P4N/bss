"""Unit: config loader YAML + env."""

import os
from pathlib import Path

from bss.config.loader import load_config


def test_yaml_defaults(tmp_path: Path, monkeypatch):
    # create minimal yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
source:
  name: binance
  base_url: "https://api.binance.com"
  timeout_seconds: 10.0
  rate_limit:
    requests_per_second: 5
    max_parallel_requests: 4
  retry:
    max_attempts: 5
    initial_delay_seconds: 1.0
    max_delay_seconds: 60.0
    backoff_factor: 2.0
loader:
  chunk_interval: "1d"
dataset:
  loader_version: "0.1.0"
  schema_version: "0.2"
storage:
  base_path: "data"
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.source_name == "binance"
    assert cfg.source_base_url == "https://api.binance.com"
    assert cfg.source_timeout == 10.0
    assert cfg.rate_limit_rps == 5
    assert cfg.chunk_interval.days == 1
    assert cfg.loader_version == "0.1.0"


def test_env_override(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
source:
  name: binance
  base_url: "https://api.binance.com"
  timeout_seconds: 10.0
  rate_limit:
    requests_per_second: 5
    max_parallel_requests: 4
  retry:
    max_attempts: 5
    initial_delay_seconds: 1.0
    max_delay_seconds: 60.0
    backoff_factor: 2.0
loader:
  chunk_interval: "1d"
dataset:
  loader_version: "0.1.0"
  schema_version: "0.2"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BSS_SOURCE_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("BSS_LOADER_CHUNK_INTERVAL", "12h")
    monkeypatch.setenv("BSS_RATE_LIMIT_RPS", "10")
    cfg = load_config(cfg_path)
    assert cfg.source_base_url == "http://localhost:9999"
    assert cfg.chunk_interval.total_seconds() == 12 * 3600
    assert cfg.rate_limit_rps == 10


def test_chunk_interval_parsing():
    from bss.config.loader import _parse_interval
    from datetime import timedelta

    assert _parse_interval("1d") == timedelta(days=1)
    assert _parse_interval("12h") == timedelta(hours=12)
    assert _parse_interval("30m") == timedelta(minutes=30)


def test_binance_url_timeout_from_config():
    # ensure config provides binance url/timeout
    cfg = load_config()  # default.yaml
    assert cfg.source_base_url.startswith("http")
    assert cfg.source_timeout > 0
    assert cfg.retry_max_attempts == 5
