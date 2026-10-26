"""Run explicitly in a disposable cloud container; never opens a PDF viewer."""

import hashlib
import json
import os
import re
import sys
import tempfile
import zlib
from pathlib import Path

import fetch_crossref
import fetch_url
import safe_http
from pdf_utils import is_valid_pdf

DOI = "10.1371/journal.pone.0000001"
PLOS = "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0000001&type=printable"


def contains_text(content, text, budget=16 * 1024 * 1024):
    """Search raw bytes and at most 128 bounded Flate streams, without a PDF parser."""
    needle = text.encode("utf-8")
    if (
        needle in content
        or text.encode("utf-16-be") in content
        or text.encode("utf-16-le") in content
    ):
        return True
    for index, marker in enumerate(re.finditer(rb"\bstream\r?\n", content)):
        if index >= 128 or budget <= 0:
            break
        start = marker.end()
        end = content.find(b"endstream", start)
        header = content[max(0, marker.start() - 2048) : marker.start()]
        if end < 0 or b"/FlateDecode" not in header:
            continue
        try:
            decoded = zlib.decompressobj().decompress(
                content[start:end], min(budget, 2 * 1024 * 1024)
            )
        except zlib.error:
            continue
        budget -= len(decoded)
        if needle in decoded:
            return True
        # A DOI can be split between adjacent PDF text literals.
        tail = b""
        for literal in re.finditer(rb"\(([^()]*)\)", decoded):
            combined = tail + literal.group(1)
            if needle in combined:
                return True
            tail = combined[-len(needle) :]
    return False


def main():
    forbidden = (
        "EZPROXY_BASE",
        "EZPROXY_COOKIES",
        "ISTEX_ACCESSTOKEN",
        "ZOTERO_DB_PATH",
        "ZOTERO_DATA_DIR",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    )
    assert not any(os.environ.get(key) for key in forbidden)
    destinations = []
    requests = []

    def audit(event, args):
        if event == "socket.connect":
            destinations.append(list(args[1]))

    sys.addaudithook(audit)
    original_send = safe_http.Session.send

    def observe(session, request, **kwargs):
        result = original_send(session, request, **kwargs)
        requests.append(
            {
                "url": request.url,
                "status": result.status_code,
                "content_disposition": result.headers.get("Content-Disposition"),
                "tls_verified": kwargs["verify"] is True,
                "has_credentials": any(
                    key in request.headers for key in ("Cookie", "Authorization")
                ),
            }
        )
        return result

    safe_http.Session.send = observe
    report = {"doi": DOI, "requests": requests, "socket_destinations": destinations}
    try:
        with tempfile.TemporaryDirectory(prefix="doifetch-oa-") as output:
            result = fetch_crossref.fetch_pdf(DOI, "public-plos-test", output)
            report["crossref"] = result
            if (
                result["status"] == "failed"
                and result["error"] == "No open access PDF found in Crossref"
            ):
                result = fetch_url.fetch_pdf(PLOS, "public-plos-test", output)
                report["plos_fallback"] = result
            assert result["status"] == "success", result
            path = Path(output) / result["file_name"]
            assert is_valid_pdf(path)
            content = path.read_bytes()
            metadata = safe_http.get(f"https://api.crossref.org/works/{DOI}").json()[
                "message"
            ]
            assert metadata["DOI"].lower() == DOI
            identity_doi = contains_text(content, DOI)
            identity_title = any(
                contains_text(content, title)
                for title in metadata.get("title", [])
                if len(title) >= 30
            )
            identity = identity_doi or identity_title
            report.update(
                {
                    "title": metadata.get("title"),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "doi_present_in_bounded_pdf_bytes": identity_doi,
                    "exact_title_present_in_bounded_pdf_bytes": identity_title,
                    "identity_method": "raw bytes and bounded Flate text streams",
                    "matches_first_download_sha256": hashlib.sha256(content).hexdigest()
                    == "22f2423f45940809cc040415b5045a707b907fddec6a0c43bea16ac6455c72b0",
                    "lightweight_pdf_validation": True,
                }
            )
            assert identity, (
                "DOI or exact title not found in bounded byte inspection; do not claim verified identity"
            )
            assert all(r["tls_verified"] and not r["has_credentials"] for r in requests)
            report["passed"] = True
    finally:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
