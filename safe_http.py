"""Bounded HTTP GETs with verified TLS and public-only connections.

No environment proxies or netrc credentials are inherited. DNS is checked where
the socket is opened, and the connection uses that checked numeric address.
"""

import ipaddress
import os
import re
import socket
from urllib.parse import urljoin, urlsplit

import requests
from requests import RequestException
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection

from config import TIMEOUT

DEFAULT_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5


def max_download_bytes():
    value = int(
        os.environ.get("DOIFETCH_MAX_DOWNLOAD_BYTES", DEFAULT_MAX_DOWNLOAD_BYTES)
    )
    if value <= 0:
        raise ValueError("DOIFETCH_MAX_DOWNLOAD_BYTES must be positive")
    return value


def validate_url(url):
    """Reject ambiguous authorities, credentials, local names and unsafe schemes."""
    try:
        if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
            raise ValueError
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise ValueError
        if p.username is not None or p.password is not None or "%" in p.netloc:
            raise ValueError
        if p.port not in (None, 80, 443):
            raise ValueError
        host = p.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
                raise ValueError
        else:
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or getattr(address, "ipv4_mapped", None)
            ):
                raise ValueError
        return p.scheme, host, p.port or (443 if p.scheme == "https" else 80)
    except (ValueError, UnicodeError, AttributeError):
        raise RequestException("Unsafe URL destination") from None


def in_scope(host, base):
    return host == base or host.endswith("." + base)


def public_addresses(host, port):
    """Reject the entire DNS answer if any address is not globally routable."""
    results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in results))
    if not addresses:
        raise RequestException("Destination has no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            not ip.is_global
            or ip.is_multicast
            or ip.is_reserved
            or getattr(ip, "ipv4_mapped", None)
            or getattr(ip, "sixtofour", None)
            or getattr(ip, "teredo", None)
        ):
            raise RequestException("Destination resolves to a non-public address")
    return addresses


class _PublicConnection:
    def _new_conn(self):
        try:
            addresses = public_addresses(self._dns_host, self.port)
            for address in addresses:
                try:
                    return create_connection(
                        (address, self.port),
                        timeout=self.timeout,
                        source_address=self.source_address,
                        socket_options=self.socket_options,
                    )
                except OSError:
                    continue
            raise OSError("No public address could be reached")
        except (OSError, ValueError, RequestException) as exc:
            raise NewConnectionError(self, "Public connection failed") from exc


class _HTTPConnection(_PublicConnection, HTTPConnection):
    pass


class _HTTPSConnection(_PublicConnection, HTTPSConnection):
    pass


class _HTTPPool(HTTPConnectionPool):
    ConnectionCls = _HTTPConnection


class _HTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _HTTPSConnection


class _PublicAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        # Copy per manager: never change urllib3's process-wide pool registry.
        self.poolmanager.pool_classes_by_scheme = {
            "http": _HTTPPool,
            "https": _HTTPSPool,
        }


class Session(requests.Session):
    """GET session; optional cookie scope confines every request to an EZproxy."""

    def __init__(self, cookie_scope=None):
        super().__init__()
        self.trust_env = False
        self.cookie_scope = cookie_scope
        self.mount("http://", _PublicAdapter())
        self.mount("https://", _PublicAdapter())

    def resolve_redirects(self, *args, **kwargs):
        # Session.send otherwise consumes redirect bodies while building _next.
        # Redirects are handled here before reading any untrusted response body.
        return iter(())

    def get(
        self,
        url,
        *,
        headers=None,
        params=None,
        timeout=TIMEOUT,
        verify=True,
        allow_redirects=True,
        stream=False,
    ):
        if verify is not True:
            raise RequestException("TLS verification cannot be disabled")
        limit = max_download_bytes()
        initial = None
        previous = None
        for hop in range(MAX_REDIRECTS + 1):
            origin = validate_url(url)
            if self.cookie_scope and (
                origin[0] != "https" or not in_scope(origin[1], self.cookie_scope)
            ):
                raise RequestException(
                    "EZproxy request left the configured HTTPS scope"
                )
            if previous and previous[0] == "https" and origin[0] != "https":
                raise RequestException("HTTPS downgrade redirect rejected")
            initial = initial or origin
            request = requests.Request("GET", url, headers=headers, params=params)
            prepared = self.prepare_request(request)
            # Validate the URL after Requests' normalization as well.
            if validate_url(prepared.url) != origin:
                raise RequestException("URL authority changed during preparation")
            if origin != initial:
                for name in list(prepared.headers):
                    if name.lower() not in ("user-agent", "accept", "accept-encoding"):
                        if name.lower() == "cookie" and self.cookie_scope:
                            continue
                        del prepared.headers[name]
            # No caller-controlled Host can disagree with the TLS/DNS destination.
            prepared.headers.pop("Host", None)
            response = self.send(
                prepared,
                timeout=timeout or TIMEOUT,
                verify=True,
                allow_redirects=False,
                stream=True,
                proxies={},
            )
            try:
                if allow_redirects and response.status_code in (
                    301,
                    302,
                    303,
                    307,
                    308,
                ):
                    location = response.headers.get("Location")
                    if location:
                        if hop == MAX_REDIRECTS:
                            raise RequestException("Too many redirects")
                        url = urljoin(prepared.url, location)
                        params = None
                        previous = origin
                        continue
                length = response.headers.get("Content-Length")
                if length is not None and (
                    not re.fullmatch(r"[0-9]+", length) or int(length) > limit
                ):
                    raise RequestException("Invalid or oversized Content-Length")
                chunks = []
                size = 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > limit:
                        raise RequestException("Response exceeds maximum download size")
                    chunks.append(chunk)
                if length is not None and not response.headers.get("Content-Encoding"):
                    if size != int(length):
                        raise RequestException("Truncated or malformed response body")
                response._content = b"".join(chunks)
                response._content_consumed = True
                return response
            finally:
                response.close()
        raise RequestException("Too many redirects")


def get(url, **kwargs):
    with Session() as session:
        return session.get(url, **kwargs)
