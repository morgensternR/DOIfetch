"""Tests for the Sci-Hub / SciDB fetcher."""

import pytest

import fetch_scihub

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000 + b"\n%%EOF\n"


class _FakeResp:
    def __init__(self, content=b""):
        self.content = content
        self.status_code = 200

    def iter_content(self, chunk_size=1024):
        yield self.content


def test_build_query_urls_tries_scihub_then_scidb():
    urls = fetch_scihub.build_query_urls("10.1000/example", "Some Paper")
    # Classic Sci-Hub pages come first (frozen corpus, freely scrapable).
    assert urls[0] == "https://sci-hub.fr/10.1000/example"
    # SciDB (Anna's Archive) uses the /scidb/<doi> path and comes after.
    scidb = [u for u in urls if "annas-archive" in u]
    assert scidb, "expected at least one SciDB candidate"
    assert all(u.endswith("scidb/10.1000/example") for u in scidb)
    # Sci-Hub candidates precede SciDB candidates.
    assert urls.index("https://sci-hub.fr/10.1000/example") < urls.index(scidb[0])


def test_build_query_urls_title_search_when_no_doi():
    urls = fetch_scihub.build_query_urls("", "Cognitive Constraints")
    assert urls
    assert all("?s=" in u for u in urls)
    # Title search is a Sci-Hub feature only; SciDB has no search endpoint here.
    assert not any("scidb/" in u for u in urls)


def test_extract_pdf_url_from_iframe():
    html = b'<html><body><iframe src="https://sci-hub.se/downloads/x.pdf"></iframe></body></html>'
    assert fetch_scihub.extract_pdf_url(html) == "https://sci-hub.se/downloads/x.pdf"


def test_extract_pdf_url_from_embed():
    html = b'<html><embed src="https://annas-archive.se/scidb/file.pdf"></html>'
    assert (
        fetch_scihub.extract_pdf_url(html) == "https://annas-archive.se/scidb/file.pdf"
    )


def test_extract_pdf_url_handles_protocol_relative():
    html = b'<iframe src="//sci-hub.se/downloads/y.pdf"></iframe>'
    assert fetch_scihub.extract_pdf_url(html) == "https://sci-hub.se/downloads/y.pdf"


def test_extract_pdf_url_none_when_no_embed():
    assert (
        fetch_scihub.extract_pdf_url(b"<html><body>no pdf here</body></html>") is None
    )


def test_extract_pdf_url_none_when_src_not_http():
    assert fetch_scihub.extract_pdf_url(b'<iframe src="about:blank"></iframe>') is None


def _dispatch(viewer_html, pdf_bytes):
    """requests.get replacement: viewer pages return HTML, the PDF URL returns bytes."""

    def fake_get(url, **kwargs):
        if url.endswith(".pdf"):
            return _FakeResp(content=pdf_bytes)
        return _FakeResp(content=viewer_html)

    return fake_get


def test_fetch_pdf_success_via_embedded_viewer(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_scihub.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        fetch_scihub.requests,
        "get",
        _dispatch(
            b'<iframe src="https://sci-hub.se/downloads/paper.pdf"></iframe>',
            VALID_PDF,
        ),
    )
    result = fetch_scihub.fetch_pdf(
        "10.1000/example", "Some Paper", output_dir=str(tmp_path)
    )
    assert result["status"] == "success"
    assert (tmp_path / result["file_name"]).exists()


def test_fetch_pdf_failed_when_no_link(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_scihub.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        fetch_scihub.requests,
        "get",
        _dispatch(b"<html><body>not available</body></html>", VALID_PDF),
    )
    result = fetch_scihub.fetch_pdf(
        "10.1000/example", "Some Paper", output_dir=str(tmp_path)
    )
    assert result["status"] == "failed"
    assert "PDF link not found" in result["error"]


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<iframe src="https://acceptable.a-ads.com/2425588/?size=Adaptive"></iframe>',
            None,
        ),
        (
            '<iframe src="https://ads.example/banner"></iframe><iframe src="//papers.example/paper.pdf"></iframe>',
            "https://papers.example/paper.pdf",
        ),
        (
            '<iframe src="https://ads.example/banner"></iframe><embed src="https://papers.example/paper.pdf">',
            "https://papers.example/paper.pdf",
        ),
        (
            '<iframe></iframe><embed src="https://papers.example/paper.pdf">',
            "https://papers.example/paper.pdf",
        ),
        (
            '<embed type="application/pdf" src="https://papers.example/download?id=42">',
            "https://papers.example/download?id=42",
        ),
        (
            '<iframe id="pdf" src="//papers.example/download?id=42"></iframe>',
            "https://papers.example/download?id=42",
        ),
        (
            '<iframe src="https://papers.example/PAPER.PDF?download=1#page=2"></iframe>',
            "https://papers.example/PAPER.PDF?download=1#page=2",
        ),
        (
            '<iframe src="https://ads.example/banner?name=paper.pdf#paper.pdf"></iframe>',
            None,
        ),
        ('<iframe id="pdf" src="javascript:alert(1)"></iframe>', None),
        (
            '<embed type="application/pdf" src="https://user:password@papers.example/file.pdf">',
            None,
        ),
        ('<iframe src="http://127.0.0.1/paper.pdf"></iframe>', None),
    ],
)
def test_extract_pdf_url_requires_pdf_evidence(html, expected):
    assert fetch_scihub.extract_pdf_url(html.encode()) == expected


@pytest.mark.parametrize("has_pdf", [False, True])
def test_fetch_pdf_never_requests_unmarked_ad_iframe(monkeypatch, tmp_path, has_pdf):
    mirror = "https://mirror.example/"
    pdf_url = "https://papers.example/paper.pdf"
    html = (
        b'<iframe src="https://acceptable.a-ads.com/2425588/?size=Adaptive"></iframe>'
    )
    if has_pdf:
        html += f'<embed src="{pdf_url}">'.encode()
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == mirror + "10.1000/example":
            return _FakeResp(html)
        if url == pdf_url:
            return _FakeResp(VALID_PDF)
        pytest.fail(f"Unexpected request to unrelated iframe: {url}")

    monkeypatch.setattr(fetch_scihub, "SCI_HUB_DOMAINS", [mirror])
    monkeypatch.setattr(fetch_scihub, "SCIDB_DOMAINS", [])
    monkeypatch.setattr(fetch_scihub.time, "sleep", lambda *_: None)
    monkeypatch.setattr(fetch_scihub.requests, "get", fake_get)
    result = fetch_scihub.fetch_pdf("10.1000/example", "Paper", str(tmp_path))
    assert calls == [mirror + "10.1000/example"] + ([pdf_url] if has_pdf else [])
    assert result["status"] == ("success" if has_pdf else "failed")
    if has_pdf:
        assert (tmp_path / result["file_name"]).read_bytes() == VALID_PDF
    else:
        assert not list(tmp_path.iterdir())
