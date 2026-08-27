"""CLI integration — thin adapter."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(args, base_path: Path):
    env = dict(**__import__("os").environ)
    # Ensure src is on PYTHONPATH for subprocess
    src_path = str(Path(__file__).resolve().parents[3] / "src")
    env["PYTHONPATH"] = src_path + (__import__("os").pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "bss.historical_loader.cli.main", "--base-path", str(base_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def test_cli_happy_path(tmp_path: Path):
    res = _run_cli(["download", "--dataset-id", "ds_cli1", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M15", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-02T00:00:00Z"], tmp_path)
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["status"] == "COMPLETED"
    # replay
    res2 = _run_cli(["replay", "--dataset-id", "ds_cli1", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M15", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-02T00:00:00Z"], tmp_path)
    assert res2.returncode == 0
    lines = [json.loads(l) for l in res2.stdout.strip().splitlines() if l.strip() and l.startswith("{") and "event_type" in l]
    assert len(lines) > 0
    assert lines[0]["event_type"] == "CANDLE_CLOSED"


def test_cli_invalid_args(tmp_path: Path):
    res = _run_cli(["download", "--dataset-id", "ds_cli2"], tmp_path)
    assert res.returncode != 0
    # argparse error to stderr
    assert "required" in res.stderr.lower() or "error" in res.stderr.lower()


def test_cli_structured_error(tmp_path: Path):
    # invalid timeframe
    res = _run_cli(["download", "--dataset-id", "ds_cli3", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M99", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-02T00:00:00Z"], tmp_path)
    assert res.returncode != 0
    # should be JSON error to stderr
    err = json.loads(res.stderr.strip().splitlines()[-1])
    assert "error" in err


def test_cli_replay_output(tmp_path: Path):
    _run_cli(["download", "--dataset-id", "ds_cli4", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M15", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-01T01:00:00Z"], tmp_path)
    res = _run_cli(["replay", "--dataset-id", "ds_cli4", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M15", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-01T01:00:00Z"], tmp_path)
    assert res.returncode == 0
    events = [json.loads(l) for l in res.stdout.strip().splitlines() if l.strip() and "event_type" in l]
    assert len(events) == 4
    assert all(e["event_type"] == "CANDLE_CLOSED" for e in events)
    # run_id present
    assert all("run_id" in e for e in events)


def test_cli_recovery_path(tmp_path: Path):
    # create gap via direct storage manipulation, then recover
    # Use download with gap source? Instead use CLI download then corrupt, then recover
    _run_cli(["download", "--dataset-id", "ds_cli5", "--version", "v1", "--symbol", "SOLUSDT", "--timeframe", "M15", "--from", "2025-01-01T00:00:00Z", "--to", "2025-01-02T00:00:00Z"], tmp_path)
    # corrupt a chunk
    p = list((tmp_path / "normalized" / "ds_cli5" / "v1").rglob("*.jsonl"))[0]
    p.write_text("corrupt", encoding="utf-8")
    res = _run_cli(["recover", "--dataset-id", "ds_cli5", "--version", "v1"], tmp_path)
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert "recovered_ranges" in out or "is_empty" in out
