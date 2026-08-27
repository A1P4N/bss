"""Binance HTTP client — no business logic, no retry, maps HTTP to taxonomy."""

from __future__ import annotations

import http.client
import json
import socket
import urllib.parse
from typing import Any, Dict, List

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


def _parse_retry_after(headers) -> float | None:
    # headers is http.client.HTTPMessage or dict
    try:
        # try get Retry-After
        val = None
        if hasattr(headers, "get"):
            val = headers.get("Retry-After") or headers.get("retry-after")
        if val is None:
            return None
        # Try int seconds
        try:
            return float(val)
        except ValueError:
            # HTTP-date not supported for MVP, return None
            return None
    except Exception:
        return None


class BinanceClient:
    """Thin HTTP client for Binance klines."""

    def __init__(self, base_url: str = "https://api.binance.com", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> List[list[Any]]:
        """Fetch klines, map HTTP errors to taxonomy.

        start_time/end_time are ms since epoch or None.
        """
        params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        query = urllib.parse.urlencode(params)
        url = f"/api/v3/klines?{query}"

        parsed = urllib.parse.urlparse(self.base_url)
        host = parsed.hostname
        if not host:
            raise ValueError(f"invalid base_url {self.base_url!r}")
        port = parsed.port
        is_https = parsed.scheme == "https"
        path = parsed.path.rstrip("/")
        full_path = path + url if path else url

        # Use HTTP(S)Connection
        conn_cls = http.client.HTTPSConnection if is_https else http.client.HTTPConnection
        # Determine port default
        if port is None:
            port = 443 if is_https else 80

        conn = None
        try:
            conn = conn_cls(host, port, timeout=self.timeout)
            conn.request("GET", full_path, headers={"User-Agent": "bss/0.1.0"})
            resp = conn.getresponse()
            status = resp.status
            headers = resp.getheaders()
            # Convert headers to dict for parsing
            header_dict = {k: v for k, v in headers}
            body = resp.read()

            if status == 429:
                retry_after = _parse_retry_after(header_dict)
                raise RateLimitedError(message=f"429 rate limited for {symbol} {interval}", context={"status": status, "symbol": symbol, "interval": interval}, retry_after=retry_after)
            if 500 <= status <= 599:
                raise TemporaryServerError(message=f"{status} server error for {symbol}", context={"status": status})
            if status == 400:
                raise BadRequestError(message=f"400 bad request for {symbol}", context={"status": status})
            if status == 401:
                raise UnauthorizedError(message=f"401 unauthorized", context={"status": status})
            if status == 403:
                raise ForbiddenError(message=f"403 forbidden", context={"status": status})
            if status == 404:
                raise NotFoundError(message=f"404 not found for {symbol}", context={"status": status})
            if status == 422:
                from bss.historical_loader.domain.errors import PermanentError

                raise PermanentError(code="UNPROCESSABLE", message=f"422 for {symbol}", context={"status": status})
            if status < 200 or status >= 300:
                # treat other 4xx as permanent, 5xx already handled
                if 400 <= status < 500:
                    raise BadRequestError(message=f"{status} for {symbol}", context={"status": status})
                raise TemporaryServerError(message=f"{status} for {symbol}", context={"status": status})

            # success
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception as exc:
                raise TemporaryServerError(message=f"invalid json: {exc}", context={}) from exc

            if not isinstance(data, list):
                raise BadRequestError(message="invalid klines response", context={"body": body[:200].decode(errors="ignore")})

            return data

        except (RateLimitedError, TemporaryServerError, BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError):
            raise
        except socket.timeout as exc:
            raise TimeoutError(message=f"timeout for {symbol}", context={"timeout": self.timeout}) from exc
        except (socket.gaierror, ConnectionRefusedError, http.client.HTTPException, OSError) as exc:
            raise NetworkError(message=f"network error for {symbol}: {exc}", context={}) from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
