"""E2E CLI Binance download via mock server."""

import http.server
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def _mock_klines(start, end):
    # Generate M15 klines for range
    klines = []
    cur = start
    while cur < end:
        open_ms = int(cur.timestamp() * 1000)
        klines.append([open_ms, "100", "101", "99", "100", "1000", open_ms + 900000, "0", 0, "0", "0", "0"])
        cur = cur + __import__("datetime").timedelta(minutes=15)
    return klines


class Handler(http.server.BaseHTTPRequestHandler):
    klines = []

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(Handler.klines).encode())

    def log_message(self, format, *args):
        pass


def test_cli_binance_download(tmp_path: Path):
    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)
    Handler.klines = _mock_klines(start, end)
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)
    try:
        # Create config with binance base_url pointing to mock
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            f"""
source:
  name: binance
  base_url: "http://127.0.0.1:{port}"
  timeout_seconds: 5.0
  rate_limit:
    requests_per_second: 5
    max_parallel_requests: 4
  retry:
    max_attempts: 3
    initial_delay_seconds: 0.1
    max_delay_seconds: 1.0
    backoff_factor: 2.0
loader:
  chunk_interval: "1d"
dataset:
  loader_version: "0.1.0"
  schema_version: "0.2"
storage:
  base_path: "{tmp_path / "data"}"
""",
            encoding="utf-8",
        )
        env = dict(**__import__("os").environ)
        src_path = str(Path(__file__).resolve().parents[2] / "src")
        env["PYTHONPATH"] = src_path + (__import__("os").pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
        env["BSS_SOURCE_BASE_URL"] = f"http://127.0.0.1:{port}"
        # Use CLI with --source binance and --base-path
        cmd = [
            sys.executable,
            "-m",
            "bss.historical_loader.cli.main",
            "--base-path",
            str(tmp_path / "data"),
            "download",
            "--dataset-id",
            "ds_cli_binance",
            "--version",
            "v1",
            "--symbol",
            "SOLUSDT",
            "--timeframe",
            "M15",
            "--from",
            "2025-01-01T00:00:00Z",
            "--to",
            "2025-01-02T00:00:00Z",
            "--source",
            "binance",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        assert result.returncode == 0, f"CLI failed: {result.stderr} {result.stdout}"
        out = json.loads(result.stdout.strip().splitlines()[-1])
        assert out["status"] == "COMPLETED"
        # Verify storage
        assert (tmp_path / "data" / "normalized" / "ds_cli_binance" / "v1").exists()
        assert (tmp_path / "data" / "metadata" / "datasets" / "ds_cli_binance" / "v1.json").exists()
        # checkpoint complete
        assert (tmp_path / "data" / "checkpoints" / f"{out['job_id']}.json").exists()
    finally:
        server.shutdown()
