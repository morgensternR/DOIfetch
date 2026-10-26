"""Run explicitly in a disposable cloud container; never opens a PDF viewer."""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import fetch_crossref
import fetch_url
import safe_http
from pdf_utils import is_valid_pdf

DOI = "10.1371/journal.pone.0000001"
PLOS = "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0000001&type=printable"


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
            identity = DOI.encode("ascii") in content
            report.update(
                {
                    "title": metadata.get("title"),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "doi_present_in_pdf_bytes": identity,
                    "lightweight_pdf_validation": True,
                }
            )
            assert identity, (
                "DOI identity not present in raw PDF bytes; do not claim verified identity"
            )
            assert all(r["tls_verified"] and not r["has_credentials"] for r in requests)
            report["passed"] = True
    finally:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
