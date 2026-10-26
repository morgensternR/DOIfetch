"""Security regressions use synthetic responses and files, never real credentials."""

import socket

import pytest
import requests as real_requests
from requests.structures import CaseInsensitiveDict

import fetch_crossref
import fetch_ezproxy
import fetch_url
import pdf_utils
import safe_http

PDF = b"%PDF-1.7\n" + b"0" * 2000 + b"\n%%EOF\n"


class Response:
    def __init__(self, body=PDF, status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers or {})
        self.body = body
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size):
        yield from self.chunks if self.chunks is not None else [self.body]

    def close(self):
        self.closed = True


def transport(monkeypatch, responses, scope=None):
    session = safe_http.Session(cookie_scope=scope)
    sent = []

    def send(request, **kwargs):
        sent.append((request, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(session, "send", send)
    return session, sent


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.org/a",
        "//example.org/a",
        "https://user:secret@example.org/a",
        "https://example.org:8080/a",
        "https://127.0.0.1/a",
        "http://10.0.0.1/a",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1]/",
        "http://localhost/",
        "http://printer.local/",
        "http://server/",
        "http://224.0.0.1/",
        "https://example.org\\@evil.org/",
        "https://example.org/\n",
        "https://example%2eorg/",
        "http://100.64.0.1/",
    ],
)
def test_invalid_destinations_rejected_before_send(monkeypatch, url):
    session, sent = transport(monkeypatch, [])
    with pytest.raises(safe_http.RequestException):
        session.get(url)
    assert not sent


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.1.2.3"],
        ["169.254.169.254"],
        ["::1"],
        ["93.184.216.34", "192.168.1.1"],
        ["::ffff:93.184.216.34"],
        ["64:ff9b::a00:1"],
        ["2002:0a00:0001::1"],
    ],
)
def test_dns_rejects_nonpublic_and_mixed_answers(monkeypatch, addresses):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses
        ],
    )
    with pytest.raises(safe_http.RequestException):
        safe_http.public_addresses("example.org", 443)


def test_connection_pins_checked_ip_and_keeps_tls_hostname(monkeypatch):
    resolutions = []
    connections = []

    def resolve(host, port, **kwargs):
        resolutions.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(
        safe_http, "create_connection", lambda target, **k: connections.append(target)
    )
    conn = safe_http._HTTPSConnection("example.org", port=443, timeout=30)
    conn._new_conn()
    assert resolutions == ["example.org"]
    assert connections == [("93.184.216.34", 443)]
    assert conn.host == "example.org"


def test_tls_timeout_and_environment_credentials(monkeypatch):
    response = Response()
    session, sent = transport(monkeypatch, [response])
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    session.get("https://example.org/a")
    assert session.trust_env is False
    kwargs = sent[0][1]
    assert kwargs["verify"] is True
    assert kwargs["timeout"] > 0
    assert kwargs["allow_redirects"] is False
    assert kwargs["proxies"] == {}
    assert response.closed


def test_tls_cannot_be_disabled(monkeypatch):
    session, sent = transport(monkeypatch, [])
    with pytest.raises(safe_http.RequestException, match="TLS"):
        session.get("https://example.org", verify=False)
    assert not sent


def test_tls_failure_is_not_retried_insecurely(monkeypatch):
    session = safe_http.Session()
    calls = []

    def fail(request, **kwargs):
        calls.append(kwargs)
        raise real_requests.exceptions.SSLError("synthetic broken certificate")

    monkeypatch.setattr(session, "send", fail)
    with pytest.raises(real_requests.exceptions.SSLError):
        session.get("https://example.org")
    assert len(calls) == 1
    assert calls[0]["verify"] is True


@pytest.mark.parametrize(
    "target",
    [
        "http://example.org/pdf",
        "https://127.0.0.1/pdf",
        "file:///tmp/document",
        "https://u:p@example.org/pdf",
    ],
)
def test_unsafe_redirect_rejected(monkeypatch, target):
    response = Response(status=302, headers={"Location": target})
    session, sent = transport(monkeypatch, [response])
    with pytest.raises(safe_http.RequestException):
        session.get("https://example.org/start")
    assert len(sent) == 1
    assert response.closed


def test_cross_origin_redirect_strips_credentials(monkeypatch):
    session, sent = transport(
        monkeypatch,
        [
            Response(status=302, headers={"Location": "https://other.org/pdf"}),
            Response(),
        ],
    )
    session.get(
        "https://example.org",
        headers={
            "Authorization": "Bearer synthetic",
            "Cookie": "secret=synthetic",
            "X-Api-Key": "synthetic",
        },
    )
    assert "Authorization" in sent[0][0].headers
    for header in ("Authorization", "Cookie", "X-Api-Key"):
        assert header not in sent[1][0].headers


def test_relative_redirect_keeps_query_only_on_first_request(monkeypatch):
    session, sent = transport(
        monkeypatch,
        [
            Response(status=302, headers={"Location": "/pdf"}),
            Response(),
        ],
    )
    session.get("https://example.org/start", params={"q": "one"})
    assert sent[0][0].url.endswith("?q=one")
    assert sent[1][0].url == "https://example.org/pdf"


def test_redirect_loop_is_bounded(monkeypatch):
    responses = [Response(status=302, headers={"Location": "/loop"}) for _ in range(6)]
    session, sent = transport(monkeypatch, responses.copy())
    with pytest.raises(safe_http.RequestException, match="Too many"):
        session.get("https://example.org/loop")
    assert len(sent) == 6
    assert all(r.closed for r in responses)


def test_requests_does_not_consume_redirect_body(monkeypatch):
    session = safe_http.Session()
    response = real_requests.Response()
    response.status_code = 302
    response.headers["Location"] = "https://127.0.0.1/"
    response.url = "https://example.org/"
    response.raw = None
    monkeypatch.setattr(
        session.get_adapter("https://"), "send", lambda *a, **k: response
    )

    def forbidden(*a, **k):
        raise AssertionError("Redirect body must not be read")

    monkeypatch.setattr(response, "iter_content", forbidden)
    monkeypatch.setattr(response, "close", lambda: None)
    with pytest.raises(safe_http.RequestException, match="Unsafe URL"):
        session.get("https://example.org/")


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.org/",
        "https://proxy.edu.evil.org/",
        "http://proxy.edu/",
        "https://evil.org/?proxy.edu",
    ],
)
def test_ezproxy_cookie_redirect_cannot_leave_scope(monkeypatch, target):
    session, sent = transport(
        monkeypatch,
        [
            Response(status=302, headers={"Location": target}),
        ],
        scope="proxy.edu",
    )
    session.cookies.set("session", "synthetic", domain=".proxy.edu", secure=True)
    with pytest.raises(safe_http.RequestException):
        session.get("https://publisher.proxy.edu/")
    assert len(sent) == 1
    assert sent[0][0].headers["Cookie"] == "session=synthetic"


def test_ezproxy_checks_host_not_substring():
    assert (
        fetch_ezproxy.ezproxy_url("https://evil.org/a?proxy.edu", "proxy.edu")
        == "https://evil-org.proxy.edu/a?proxy.edu"
    )
    assert (
        fetch_ezproxy.ezproxy_url("https://publisher.proxy.edu/a", "proxy.edu")
        == "https://publisher.proxy.edu/a"
    )


def test_ezproxy_public_resolution_precedes_cookie_loading(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("EZPROXY_BASE", "proxy.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", str(cookies))
    events = []

    def resolve(doi, session):
        assert not list(session.cookies)
        assert session.cookie_scope is None
        events.append("resolve")
        return "https://publisher.org/a"

    def load(path):
        events.append("load")
        jar = real_requests.cookies.RequestsCookieJar()
        jar.set("proxy", "synthetic", domain=".proxy.edu", secure=True)
        jar.set("unrelated", "synthetic", domain=".publisher.org")
        jar.set("broad", "synthetic", domain=".edu")
        return jar

    def get(self, url, **kwargs):
        assert self.cookie_scope == "proxy.edu"
        assert [c.name for c in self.cookies] == ["proxy"]
        response = Response()
        response.content = PDF
        response.headers["Content-Type"] = "application/pdf"
        return response

    monkeypatch.setattr(fetch_ezproxy, "_resolve_publisher_url", resolve)
    monkeypatch.setattr(fetch_ezproxy, "_load_cookies", load)
    monkeypatch.setattr(safe_http.Session, "get", get)
    result = fetch_ezproxy.fetch_pdf("10.1/x", "Test", str(tmp_path))
    assert result["status"] == "success"
    assert events == ["resolve", "load"]


@pytest.mark.parametrize(
    "headers,chunks",
    [
        ({"Content-Length": "3001"}, [b"a"]),
        ({"Content-Length": "-1"}, [b"a"]),
        ({"Content-Length": "invalid"}, [b"a"]),
        ({}, [b"a" * 1500, b"a" * 1501]),
        ({"Content-Encoding": "gzip", "Content-Length": "100"}, [b"a" * 3001]),
        ({"Content-Length": "100"}, [b"a" * 10]),
    ],
)
def test_response_limits_and_failure_close(monkeypatch, headers, chunks):
    monkeypatch.setenv("DOIFETCH_MAX_DOWNLOAD_BYTES", "3000")
    response = Response(headers=headers, chunks=chunks)
    session, _ = transport(monkeypatch, [response])
    with pytest.raises(safe_http.RequestException):
        session.get("https://example.org/file")
    assert response.closed


def test_exact_size_limit_passes(monkeypatch):
    monkeypatch.setenv("DOIFETCH_MAX_DOWNLOAD_BYTES", str(len(PDF)))
    response = Response(headers={"Content-Length": str(len(PDF))})
    session, _ = transport(monkeypatch, [response])
    assert session.get("https://example.org/file")._content == PDF


@pytest.mark.parametrize(
    "body", [b"<html>error</html>" * 100, b"%PDF-1.7\n" + b"0" * 2000, b"%PDF-1.7"]
)
def test_invalid_file_cleanup_preserves_previous_file(tmp_path, body):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"existing")
    with pytest.raises(ValueError):
        pdf_utils.write_download(path, body)
    assert path.read_bytes() == b"existing"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["paper.pdf"]


def test_atomic_replace_failure_cleans_partial(monkeypatch, tmp_path):
    def fail(*args):
        raise OSError("synthetic full disk")

    monkeypatch.setattr(pdf_utils.os, "replace", fail)
    with pytest.raises(OSError):
        pdf_utils.write_download(tmp_path / "paper.pdf", PDF)
    assert not list(tmp_path.iterdir())


def test_oversized_file_never_created(monkeypatch, tmp_path):
    monkeypatch.setenv("DOIFETCH_MAX_DOWNLOAD_BYTES", "1000")
    with pytest.raises(ValueError):
        pdf_utils.write_download(tmp_path / "paper.pdf", PDF)
    assert not list(tmp_path.iterdir())


def test_symlink_not_followed(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(b"unchanged")
    link = tmp_path / "paper.pdf"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        pdf_utils.write_download(link, PDF)
    assert target.read_bytes() == b"unchanged"


def test_crossref_explicit_tls_and_timeout(monkeypatch, tmp_path):
    calls = []

    class Result:
        status_code = 200
        content = PDF

        def json(self):
            return {
                "message": {
                    "link": [
                        {
                            "URL": "https://example.org/paper.pdf",
                            "content-type": "application/pdf",
                            "content-version": "vor",
                        }
                    ]
                }
            }

    def get(url, **kwargs):
        calls.append(kwargs)
        return Result()

    monkeypatch.setattr(fetch_crossref.requests, "get", get)
    result = fetch_crossref.fetch_pdf("10.1/test", "Test", str(tmp_path))
    assert result["status"] == "success"
    assert len(calls) == 2
    assert all(c["verify"] is True and c["timeout"] > 0 for c in calls)


def test_source_failure_leaves_no_file(monkeypatch, tmp_path):
    def get(*args, **kwargs):
        raise real_requests.exceptions.ChunkedEncodingError("synthetic disconnect")

    monkeypatch.setattr(fetch_url.requests, "get", get)
    assert (
        fetch_url.fetch_pdf("https://example.org", "Test", str(tmp_path))["status"]
        == "failed"
    )
    assert not list(tmp_path.iterdir())


def test_identity_in_bounded_flate_stream():
    import zlib
    from cloud_open_access import contains_doi

    doi = "10.1371/journal.pone.0000001"
    compressed = zlib.compress(b"(10.1371) Tj (/journal.pone.0000001) Tj")
    content = b"<< /Filter /FlateDecode >>\nstream\n" + compressed + b"\nendstream"
    assert contains_doi(content, doi)
    assert not contains_doi(content, "10.9999/absent")


def test_identity_check_bounds_decompression():
    import zlib
    from cloud_open_access import contains_doi

    doi = "10.1371/journal.pone.0000001"
    compressed = zlib.compress(b"x" * 10000 + doi.encode())
    content = b"<< /Filter /FlateDecode >>\nstream\n" + compressed + b"\nendstream"
    assert not contains_doi(content, doi, budget=100)


def test_identity_check_handles_invalid_compression():
    from cloud_open_access import contains_doi

    assert not contains_doi(
        b"<< /Filter /FlateDecode >>\nstream\nnot zlib\nendstream", "10.1/test"
    )
