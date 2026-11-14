"""HTTP helper for the X1 data pipeline.

Standard library only, so the scheduled GitHub Actions job needs no dependency
install step. Every request identifies itself with a desktop User-Agent because
NFL.com rejects some default agent strings.
"""

from __future__ import annotations

import gzip
import io
import random
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
}

_SSL_CONTEXT = ssl.create_default_context()


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    body: str
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200 and bool(self.body)


def fetch(
    url: str,
    *,
    timeout: float = 45.0,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: float = 0.4,
) -> FetchResult:
    """Fetch `url` and return text. Never raises; errors land in `.error`."""
    last_error: Optional[str] = None
    status = 0
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT) as response:
                raw = response.read()
                status = response.status
                final_url = response.geturl()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            body = raw.decode("utf-8", "replace")
            time.sleep(sleep)
            return FetchResult(url=url, final_url=final_url, status=status, body=body)
        except urllib.error.HTTPError as exc:
            status = exc.code
            last_error = f"HTTP {exc.code} {exc.reason}"
        except Exception as exc:  # noqa: BLE001 - network code must be total
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(backoff * attempt + random.random())
    return FetchResult(url=url, final_url=url, status=status, body="", error=last_error)
