"""Unit: Binance client error mapping."""

import http.server
import json
import socket
import threading
import time

import pytest

from bss.historical_loader.domain.errors import (
    BadRequestError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    TemporaryServerError,
    TimeoutError,
    UnauthorizedError,
)
from bss.historical_loader.infrastructure.sources.binance.client import BinanceClient


class MockHandler(http.server.BaseHTTPRequestHandler):
    # class variable to control response
    response_code = 200
    response_body = b"[]"
    headers = {}

    def do_GET(self):
        self.send_response(self.__class__.response_code)
        for k, v in self.__class__.headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(self.__class__.response_body)

    def log_message(self, format, *args):
        pass


def _start_server(response_code, body, headers=None):
    MockHandler.response_code = response_code
    MockHandler.response_body = body if isinstance(body, bytes) else json.dumps(body).encode()
    MockHandler.headers = headers or {}
    server = http.server.HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # wait a bit
    time.sleep(0.05)
    return server, port


def test_429_with_retry_after():
    server, port = _start_server(429, b"{}", headers={"Retry-After": "5"})
    client = BinanceClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(RateLimitedError) as exc:
            client.fetch_klines("SOLUSDT", "15m")
        assert exc.value.retry_after == 5.0
    finally:
        server.shutdown()


def test_429_without_retry_after():
    server, port = _start_server(429, b"{}")
    client = BinanceClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(RateLimitedError) as exc:
            client.fetch_klines("SOLUSDT", "15m")
        assert exc.value.retry_after is None
    finally:
        server.shutdown()


@pytest.mark.parametrize("code", [500, 502, 503])
def test_5xx_retryable(code):
    server, port = _start_server(code, b"{}")
    client = BinanceClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(TemporaryServerError):
            client.fetch_klines("SOLUSDT", "15m")
    finally:
        server.shutdown()


def test_timeout():
    # Use non-routable address with short timeout
    client = BinanceClient(base_url="http://10.255.255.1:81", timeout=0.1)
    with pytest.raises((TimeoutError, NetworkError)):
        client.fetch_klines("SOLUSDT", "15m")


def test_connection_error():
    client = BinanceClient(base_url="http://127.0.0.1:1", timeout=1.0)
    with pytest.raises((NetworkError, TimeoutError)):
        client.fetch_klines("SOLUSDT", "15m")


@pytest.mark.parametrize("code,exc_type", [(400, BadRequestError), (401, UnauthorizedError), (403, ForbiddenError), (404, NotFoundError)])
def test_400_no_retry(code, exc_type):
    server, port = _start_server(code, b"{}")
    client = BinanceClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(exc_type):
            client.fetch_klines("SOLUSDT", "15m")
    finally:
        server.shutdown()


def test_422_no_retry():
    server, port = _start_server(422, b"{}")
    client = BinanceClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(Exception) as exc:
            client.fetch_klines("SOLUSDT", "15m")
        # should be PermanentError (code UNPROCESSABLE) not retryable
        assert "422" in str(exc.value) or exc.value.code == "UNPROCESSABLE"
    finally:
        server.shutdown()
