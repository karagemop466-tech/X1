"""Minimal HTTP client (stdlib only) with caching and retry.

The collector runs on GitHub Actions runners, which have unrestricted egress.
Using :mod:`urllib` avoids adding a dependency, which keeps the workflow free of
an install step and the code auditable.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

#: Official NFL endpoints are rate-sensitive; stay polite and cache hard.
DEFAULT_CACHE = Path(os.environ.get("NFLX_CACHE", ".cache/nflx"))


@dataclass
class Fetch:
    """The result of one HTTP retrieval."""

    url: str
    status: int
    body: bytes
    content_type: str
    from_cache: bool
    fetched_at: str

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding, errors="replace")


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int, detail: str = ""):
        super().__init__(f"HTTP {status} for {url} {detail}".strip())
        self.url = url
        self.status = status


class Fetcher:
    """Fetches URLs, caching responses on disk keyed by URL."""

    def __init__(self, cache_dir: Optional[Path] = None, ttl_seconds: int = 900):
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE)
        self.ttl = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._ssl = ssl.create_default_context()

    # -- cache helpers -----------------------------------------------------
    def _paths(self, url: str):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.bin", self.cache_dir / f"{digest}.meta.json"

    def read_cache(self, url: str, max_age: Optional[int] = None):
        body_path, meta_path = self._paths(url)
        if not body_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        max_age = self.ttl if max_age is None else max_age
        if max_age >= 0 and (time.time() - meta.get("epoch", 0)) > max_age:
            return None
        return (
            Fetch(
                url=url,
                status=meta.get("status", 0),
                body=body_path.read_bytes(),
                content_type=meta.get("content_type", ""),
                from_cache=True,
                fetched_at=meta.get("fetched_at", ""),
            )
        )

    def _write_cache(self, url: str, result: Fetch) -> None:
        body_path, meta_path = self._paths(url)
        body_path.write_bytes(result.body)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "status": result.status,
                    "content_type": result.content_type,
                    "epoch": time.time(),
                    "fetched_at": result.fetched_at,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- public API --------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        use_cache: bool = True,
        max_age: Optional[int] = None,
        retries: int = 3,
        timeout: int = 60,
    ) -> Fetch:
        if use_cache:
            cached = self.read_cache(url, max_age=max_age)
            if cached is not None:
                return cached

        last_error: Optional[Exception] = None
        for attempt in range(retries):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Encoding": "gzip, deflate",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                with urllib.request.urlopen(request, timeout=timeout, context=self._ssl) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    result = Fetch(
                        url=url,
                        status=response.status,
                        body=raw,
                        content_type=response.headers.get("Content-Type", ""),
                        from_cache=False,
                        fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    )
                self._write_cache(url, result)
                return result
            except urllib.error.HTTPError as exc:  # noqa: PERF203
                last_error = HttpError(url, exc.code, exc.reason or "")
                if exc.code in (400, 401, 403, 404, 410):
                    break
            except Exception as exc:  # network hiccup, DNS, timeout
                last_error = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

        if isinstance(last_error, HttpError):
            raise last_error
        raise HttpError(url, 0, str(last_error))

    def get_json(self, url: str, **kwargs):
        result = self.get(url, **kwargs)
        return json.loads(result.text())

    def manifest(self) -> Dict[str, dict]:
        """Return a manifest of every cached URL (used for provenance)."""
        out: Dict[str, dict] = {}
        for meta_path in sorted(self.cache_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            out[meta.get("url", meta_path.stem)] = {
                "status": meta.get("status"),
                "fetched_at": meta.get("fetched_at"),
                "content_type": meta.get("content_type"),
            }
        return out
