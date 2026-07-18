"""Fail-closed outbound HTTP fetcher for user-controlled URLs (ADR-0014)."""

from __future__ import annotations

import ipaddress
import socket
import ssl
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

DEFAULT_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/html",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
    }
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class SafeFetchError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class SafeFetchResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.lower() == "charset" and value.strip():
                charset = value.strip().strip(chr(34))
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


class _PinnedBackend(httpcore.SyncBackend):
    """Keep TLS SNI/Host on the original hostname while connecting to a vetted IP."""

    def __init__(self, hostname: str, address: str):
        self._backend = httpcore.SyncBackend()
        self._hostname = hostname.lower().rstrip(".")
        self._address = address

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        connect_host = self._address if host.lower().rstrip(".") == self._hostname else host
        return self._backend.connect_tcp(
            connect_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedTransport(httpx.HTTPTransport):
    def __init__(self, hostname: str, address: str):
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            retries=0,
            network_backend=_PinnedBackend(hostname, address),
        )


Resolver = Callable[[str, int], Iterable[str]]


def _system_resolver(hostname: str, port: int) -> Iterable[str]:
    rows = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return [row[4][0] for row in rows]


class SafeOutboundFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = _system_resolver,
        timeout_s: float = 15.0,
        max_redirects: int = 3,
        max_compressed_bytes: int = 2_000_000,
        max_bytes: int = 2_000_000,
    ):
        self._resolver = resolver
        self._timeout_s = timeout_s
        self._max_redirects = max_redirects
        self._max_compressed_bytes = max_compressed_bytes
        self._max_bytes = max_bytes

    def validate(self, url: str) -> ValidatedTarget:
        cleaned = (url or "").strip()
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SafeFetchError("ต้องเป็น URL แบบ http(s)")
        if parsed.username is not None or parsed.password is not None:
            raise SafeFetchError("URL ที่มี credentials ถูกปฏิเสธ")
        hostname = parsed.hostname.lower().rstrip(".")
        if not hostname or "%" in hostname:
            raise SafeFetchError("hostname ไม่ถูกต้อง")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            literal = ipaddress.ip_address(hostname)
            addresses = (str(literal),)
        except ValueError:
            try:
                addresses = tuple(
                    sorted(
                        {str(ipaddress.ip_address(item)) for item in self._resolver(hostname, port)}
                    )
                )
            except Exception as exc:
                raise SafeFetchError("DNS resolve ไม่สำเร็จ") from exc
        if not addresses:
            raise SafeFetchError("DNS ไม่คืน A/AAAA address")
        unsafe = [address for address in addresses if not ipaddress.ip_address(address).is_global]
        if unsafe:
            raise SafeFetchError("URL resolve ไปยัง non-global/internal IP")
        return ValidatedTarget(cleaned, hostname, port, addresses)

    def _decode_body(self, raw: bytes, encoding: str) -> bytes:
        try:
            encoding = encoding.strip().lower()
            if encoding in {"", "identity"}:
                body = raw
            elif encoding == "gzip":
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                body = decoder.decompress(raw, self._max_bytes + 1)
                if len(body) <= self._max_bytes:
                    body += decoder.flush(self._max_bytes + 1 - len(body))
            elif encoding == "deflate":
                decoder = zlib.decompressobj()
                body = decoder.decompress(raw, self._max_bytes + 1)
                if len(body) <= self._max_bytes:
                    body += decoder.flush(self._max_bytes + 1 - len(body))
            else:
                raise SafeFetchError("content-encoding ไม่ได้รับอนุญาต")
        except zlib.error as exc:
            raise SafeFetchError("response compression ไม่ถูกต้อง") from exc
        if len(body) > self._max_bytes:
            raise SafeFetchError("decompressed response ใหญ่เกินกำหนด")
        return body

    def _validate_response_headers(
        self,
        headers: dict[str, str],
        allowed_content_types: frozenset[str],
    ) -> None:
        content_type = headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in allowed_content_types:
            raise SafeFetchError("content-type ไม่ได้รับอนุญาต")
        raw_length = headers.get("content-length", "")
        if raw_length:
            try:
                parsed_length = int(raw_length)
            except ValueError:
                raise SafeFetchError("content-length ไม่ถูกต้อง") from None
            if parsed_length > self._max_compressed_bytes:
                raise SafeFetchError("compressed response ใหญ่เกินกำหนด")

    def _request_once(
        self,
        target: ValidatedTarget,
        address: str,
        *,
        allowed_content_types: frozenset[str],
    ) -> SafeFetchResponse:
        transport = _PinnedTransport(target.hostname, address)
        timeout = httpx.Timeout(self._timeout_s)
        headers = {
            "User-Agent": "chimlang-safe-fetch/1.0",
            "Accept-Encoding": "gzip, deflate",
        }
        with httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream("GET", target.url, headers=headers) as response:
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                if response.status_code in REDIRECT_STATUSES:
                    return SafeFetchResponse(
                        target.url,
                        response.status_code,
                        response_headers,
                        b"",
                    )
                self._validate_response_headers(response_headers, allowed_content_types)
                raw = bytearray()
                for chunk in response.iter_raw():
                    raw.extend(chunk)
                    if len(raw) > self._max_compressed_bytes:
                        raise SafeFetchError("compressed response ใหญ่เกินกำหนด")
                content = self._decode_body(
                    bytes(raw),
                    response_headers.get("content-encoding", ""),
                )
                return SafeFetchResponse(
                    target.url,
                    response.status_code,
                    response_headers,
                    content,
                )

    def fetch(
        self,
        url: str,
        *,
        allowed_content_types: frozenset[str] = DEFAULT_CONTENT_TYPES,
    ) -> SafeFetchResponse:
        current = (url or "").strip()
        previous_scheme = ""
        for hop in range(self._max_redirects + 1):
            target = self.validate(current)
            scheme = urlparse(target.url).scheme
            if previous_scheme == "https" and scheme != "https":
                raise SafeFetchError("HTTPS redirect downgrade ถูกปฏิเสธ")
            previous_scheme = scheme
            response = None
            last_error: Exception | None = None
            for address in target.addresses:
                try:
                    response = self._request_once(
                        target,
                        address,
                        allowed_content_types=allowed_content_types,
                    )
                    break
                except SafeFetchError:
                    raise
                except (httpx.HTTPError, OSError) as exc:
                    last_error = exc
            if response is None:
                raise SafeFetchError("เชื่อมต่อปลายทางที่ตรวจแล้วไม่สำเร็จ") from last_error
            if response.status_code in REDIRECT_STATUSES:
                location = response.headers.get("location", "").strip()
                if not location:
                    raise SafeFetchError("redirect ไม่มี Location")
                if hop >= self._max_redirects:
                    raise SafeFetchError("redirect มากเกินกำหนด")
                current = urljoin(target.url, location)
                continue
            if response.status_code >= 400:
                raise SafeFetchError(f"HTTP upstream ตอบ {response.status_code}")
            return response
        raise SafeFetchError("redirect มากเกินกำหนด")
