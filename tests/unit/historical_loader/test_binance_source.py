"""Unit: BinanceSource Protocol."""

import pathlib

from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.interfaces.historical_source import HistoricalSource
from bss.historical_loader.infrastructure.sources.binance.adapter import BinanceSource
from bss.historical_loader.infrastructure.sources.binance.client import BinanceClient


def test_binance_source_protocol():
    client = BinanceClient(base_url="http://localhost:9999", timeout=1.0)
    source = BinanceSource(client=client)
    assert isinstance(source, HistoricalSource)
    # available_range
    tr = source.available_range("SOLUSDT", Timeframe.M15)
    assert tr.start.tzinfo is not None


def test_source_no_download_job_import():
    text = pathlib.Path("src/bss/historical_loader/infrastructure/sources/binance/adapter.py").read_text()
    assert "DownloadJob" not in text
    assert "Checkpoint" not in text
    assert "from bss.replay" not in text
    assert "from bss.analysis" not in text


def test_source_no_storage_import():
    text = pathlib.Path("src/bss/historical_loader/infrastructure/sources/binance/adapter.py").read_text()
    assert "RawStorage" not in text
    assert "NormalizedStorage" not in text


def test_client_no_retry_policy():
    text = pathlib.Path("src/bss/historical_loader/infrastructure/sources/binance/client.py").read_text()
    assert "RetryPolicy" not in text
    assert "RateLimiter" not in text
