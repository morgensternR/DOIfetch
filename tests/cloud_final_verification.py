"""Explicit cloud-only source-chain check; bounded byte inspection, no PDF viewer."""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import fetch
import fetch_istex
import fetch_scihub
import safe_http
import zotero
from cloud_open_access import contains_text
from pdf_utils import is_valid_pdf

DOI = "10.1016/j.applthermaleng.2022.119951"


def main():
    forbidden = (
        "EZPROXY_BASE",
        "EZPROXY_COOKIES",
        "ISTEX_ACCESSTOKEN",
        "ZOTERO_DB_PATH",
        "ZOTERO_DATA_DIR",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    assert not any(os.environ.get(key) for key in forbidden)
    assert Path.home() == Path("/tmp/empty-home")
    assert not list(Path.home().iterdir())
    # Never probe even the disposable home's token or reference locations.
    fetch_istex._token_from_file = lambda path: ""

    def no_personal_files(*args, **kwargs):
        raise AssertionError("Personal-file discovery is forbidden in this check")

    zotero.find_zotero_db = no_personal_files
    events = []
    providers = []
    active = {"provider": "metadata"}
    report = {
        "requested_doi": DOI,
        "source_order": list(fetch.SOURCE_ORDER),
        "providers": providers,
        "events": events,
        "credentials": "none; token-file reads and Zotero discovery disabled",
        "libgen": "not attempted: ISBN-only route, not part of the existing DOI chain",
    }

    def audit(event, args):
        if event == "socket.connect":
            events.append(
                {
                    "provider": active["provider"],
                    "kind": "socket",
                    "destination": list(args[1]),
                }
            )

    sys.addaudithook(audit)
    original_send = safe_http.Session.send
    original_get = safe_http.Session.get
    original_extract = fetch_scihub.extract_pdf_url

    def observe_send(session, request, **kwargs):
        event = {
            "provider": active["provider"],
            "kind": "request",
            "url": request.url,
            "tls_verified": kwargs["verify"] is True,
            "has_credentials": any(
                k in request.headers for k in ("Cookie", "Authorization")
            ),
        }
        events.append(event)
        assert event["tls_verified"] and not event["has_credentials"]
        try:
            response = original_send(session, request, **kwargs)
            event.update(
                status=response.status_code, location=response.headers.get("Location")
            )
            return response
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise

    def observe_get(session, url, **kwargs):
        event = {"provider": active["provider"], "kind": "get", "url": url}
        events.append(event)
        try:
            response = original_get(session, url, **kwargs)
            event.update(
                status=response.status_code,
                final_url=response.url,
                bytes=len(response.content),
            )
            return response
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise

    def observe_extract(content):
        link = original_extract(content)
        events.append(
            {
                "provider": active["provider"],
                "kind": "mirror_extraction",
                "pdf_url": link,
                "result": "PDF link found" if link else "PDF link not found",
            }
        )
        return link

    safe_http.Session.send = observe_send
    safe_http.Session.get = observe_get
    fetch_scihub.extract_pdf_url = observe_extract

    def observe_provider(name, original):
        def run(*args, **kwargs):
            active["provider"] = name
            entry = {"provider": name, "event_start": len(events)}
            providers.append(entry)
            started = time.monotonic()
            output = io.StringIO()
            try:
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    result = original(*args, **kwargs)
                entry["result"] = result
                return result
            except Exception as exc:
                entry["uncaught_error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                entry.update(
                    seconds=round(time.monotonic() - started, 3),
                    event_end=len(events),
                    output=output.getvalue(),
                )

        return run

    for name in fetch.SOURCE_ORDER:
        module = fetch.SOURCES[name]
        module.fetch_pdf = observe_provider(name, module.fetch_pdf)

    try:
        metadata = {}
        title = ""
        try:
            response = safe_http.get(f"https://api.crossref.org/works/{DOI}")
            response.raise_for_status()
            metadata = response.json()["message"]
            assert metadata["DOI"].lower() == DOI
            title = metadata["title"][0]
            author = metadata.get("author", [{}])[0].get("family", "")
            year = metadata.get("published", {}).get("date-parts", [[2022]])[0][0]
            # HAL expects a normal reference label; no provider matching changes.
            label = f"{author} {year} - {title}" if author else title
            report["metadata"] = {
                "resolved_doi": metadata["DOI"],
                "title": title,
                "reference_label": label,
                "source": f"https://api.crossref.org/works/{DOI}",
            }
        except Exception as exc:
            report["metadata_error"] = f"{type(exc).__name__}: {exc}"
            label = DOI.replace("/", "_")
        with tempfile.TemporaryDirectory(prefix="doifetch-final-") as output:
            result = fetch._fetch_one(DOI, label, output, "all", zotero_db=None)
            report["chain_result"] = result
            attempted = {p["provider"] for p in providers}
            report["not_attempted"] = [
                n for n in fetch.SOURCE_ORDER if n not in attempted
            ]
            report["remaining_files"] = [p.name for p in Path(output).iterdir()]
            if result["status"] == "success":
                path = Path(output) / result["file_name"]
                content = path.read_bytes()
                doi_match = contains_text(content, DOI)
                title_match = bool(title) and contains_text(content, title)
                signature = is_valid_pdf(path)
                report["download"] = {
                    "retrieval_source": providers[-1]["provider"],
                    "resolved_doi": metadata.get("DOI"),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "lightweight_pdf_validation": signature,
                    "doi_present": doi_match,
                    "exact_title_present": title_match,
                    "identity_verified": bool(signature and doi_match and title_match),
                    "identity_method": "DOI AND Crossref title in raw bytes / bounded Flate streams",
                }
                assert report["download"]["identity_verified"], (
                    "Download obtained but correct-paper identity is not established"
                )
            else:
                report["download"] = None
                assert not report["remaining_files"], "Failure left partial files"
            report["completed"] = True
    finally:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
