"""Bounded HTTPS downloads. Redirect destinations are validated before access."""
from __future__ import annotations

import ipaddress
import json
import socket
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from .common import digest, read_json, write_json


class AuthenticationError(RuntimeError):
    """Fatal credential failure, safe to display without request details."""


class DownloadError(ValueError):
    """Expected remote failure; callers can record it and continue a batch."""


class RateLimitError(DownloadError):
    def __init__(self, retry_after=None):
        super().__init__("Provider rate limit reached; batch deferred")
        self.retry_after = retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    def __init__(self, root, config, opener=None, sleeper=time.sleep, resolver=socket.getaddrinfo):
        self.root, self.config = root, config
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.sleep, self.resolve = sleeper, resolver
        self.last_request = 0.0
        self.blocked_hosts = set()

    def check_url(self, url, allowed_hosts):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username
                or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
            raise ValueError("Provider URL is outside the HTTPS host allowlist")
        addresses = self.resolve(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Provider URL resolves to a non-public address")
        return parsed

    def get(self, url, allowed_hosts, headers=None, max_bytes=None):
        maximum = max_bytes or self.config["max_source_bytes"]
        original = url
        for attempt in range(self.config["retries"] + 1):
            current = original
            try:
                for redirect in range(4):
                    parsed = self.check_url(current, allowed_hosts)
                    if parsed.hostname in self.blocked_hosts:
                        raise DownloadError("Provider deferred after a rate-limit response")
                    delay = self.config["request_interval_seconds"] - (time.monotonic() - self.last_request)
                    if delay > 0:
                        self.sleep(delay)
                    request = urllib.request.Request(current, headers={"User-Agent": "NOX-Art-Database/1.0", **(headers or {})})
                    self.last_request = time.monotonic()
                    try:
                        response = self.opener.open(request, timeout=self.config["timeout_seconds"])
                    except urllib.error.HTTPError as error:
                        if error.code in {301, 302, 303, 307, 308}:
                            if headers and any(k.lower() == "authorization" for k in headers):
                                raise ValueError("Authenticated API redirects are not followed") from error
                            location = error.headers.get("Location")
                            error.close()
                            if not location:
                                raise ValueError("Redirect has no destination")
                            current = urljoin(current, location)
                            continue
                        raise
                    with response:
                        length = response.headers.get("Content-Length")
                        if length and int(length) > maximum:
                            raise ValueError("Download exceeds file-size limit")
                        chunks, total = [], 0
                        while True:
                            chunk = response.read(min(65536, maximum + 1 - total))
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > maximum:
                                raise ValueError("Download exceeds file-size limit")
                            chunks.append(chunk)
                        return b"".join(chunks)
                raise ValueError("Too many redirects")
            except urllib.error.HTTPError as error:
                code = error.code
                retry_after = error.headers.get("Retry-After", "")
                error.close()
                if code in {401, 403} and headers and "Authorization" in headers:
                    raise AuthenticationError(f"SteamGridDB authentication failed (HTTP {code}); check STEAMGRIDDB_API_KEY") from None
                if code == 429:
                    # Stop this host for the entire batch. Never retry before a provider's reset.
                    self.blocked_hosts.add(urlsplit(current).hostname)
                    now = time.time()
                    if retry_after.isdigit():
                        retry_at = now + int(retry_after)
                    else:
                        try:
                            retry_at = parsedate_to_datetime(retry_after).timestamp()
                        except (TypeError, ValueError):
                            retry_at = now + 3600
                    raise RateLimitError(datetime.fromtimestamp(max(now + 60, retry_at), timezone.utc).isoformat()) from None
                if code not in {500, 502, 503, 504} or attempt == self.config["retries"]:
                    raise DownloadError(f"Provider returned HTTP {code}") from None
                if retry_after and (not retry_after.isdigit() or int(retry_after) > 30):
                    self.blocked_hosts.add(urlsplit(current).hostname)
                    raise DownloadError("Provider requested a later retry") from None
                self.sleep(max(2 ** attempt, int(retry_after or 0)))
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt == self.config["retries"]:
                    raise DownloadError("Provider unavailable after bounded retries") from None
                self.sleep(2 ** attempt)
        raise ValueError("Download failed")

    def json(self, url, allowed_hosts, headers=None, refresh=False):
        cache = self.root / ".cache/metadata" / (digest(url.encode()) + ".json")
        if cache.exists() and not refresh:
            entry = read_json(cache)
            if time.time() - entry["stored_at"] < self.config["cache_hours"] * 3600:
                return entry["data"]
        data = json.loads(self.get(url, allowed_hosts, headers, max_bytes=2 * 1024 * 1024))
        write_json(cache, {"stored_at": time.time(), "data": data})
        return data
