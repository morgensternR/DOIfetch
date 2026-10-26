# DOIfetch security review — 2026-10-26

Baseline: `881878996e63f633fd91af1f69a19b1b167f7107`.
Work was performed through the GitHub connector and GitHub-hosted Ubuntu runners in the fork, never through the Windows shell or filesystem. No personal reference files, Zotero library, institutional cookie export, or token file was accessed.

## Scope and behavior

All sources remain: Sci-Hub, SciDB, Anna's Archive, LibGen (PDF and EPUB), Crossref, Unpaywall, HAL, ISTEX, EZproxy, and direct URLs. `fetch.py` and `config.py`, including source order and domain lists, are unchanged. No deployment, merge, or installation on the user's computer was performed.

Security-related behavior changes:
- HTTPS certificate and hostname verification is mandatory; a broken chain fails without an insecure retry.
- Only HTTP/HTTPS on ports 80/443 is accepted. URL credentials, local names, non-public IPs, mixed public/private DNS answers, reserved/translated IPv6 destinations, and HTTPS-to-HTTP redirects are rejected.
- Each actual new connection resolves and validates all addresses, then connects to a checked numeric address while retaining the original TLS hostname. This avoids a second hostname lookup between checking and connecting.
- Redirects are followed explicitly, up to five hops. Redirect bodies are closed without buffering. Cross-origin requests discard credential-bearing headers; environment proxies and netrc authentication are not inherited.
- EZproxy resolves the public DOI with an empty session before loading cookies. Only unexpired cookies for the configured proxy host or its subdomains are retained, forced secure, and used in a separate session. Every proxied request/redirect must remain within that HTTPS scope. Host membership uses a dot boundary, never substring matching.
- `DOIFETCH_MAX_DOWNLOAD_BYTES` sets a positive byte limit; default **52,428,800 bytes (50 MiB)**. The limit applies to all responses, including metadata and HTML, and counts streamed decoded bytes even without Content-Length. Invalid/oversized lengths and incomplete unencoded bodies fail.
- Downloads are validated in private sibling temporary files (mode 0600 on Linux), then published with atomic replacement. Failure removes temporary files and preserves an existing destination; symbolic-link destinations are refused.
- PDF screening checks size, version signature and the final EOF marker. EPUB screening checks bounded ZIP/mimetype/end-record signatures without extraction. Neither is a complete document validator.
- Python metadata now requires **3.10+**. Patched Requests requires 3.10; the baseline's evaluated union annotations already failed on 3.9. No vulnerable Python 3.9 dependency branch is retained.

## Modified files

| File | Change |
| --- | --- |
| `safe_http.py` | Shared verified TLS, public-address socket adapter, explicit redirects, credential isolation, response limits and closing. |
| `pdf_utils.py` | Bounded structural screening and private temporary-file publication/cleanup. |
| `fetch_crossref.py` | Restore explicit TLS verification/timeouts, remove HTTPS warning suppression, use shared HTTP and file writer. |
| `fetch_unpaywall.py` | Remove HTTPS warning suppression; use shared HTTP and file writer. |
| `fetch_ezproxy.py` | Separate public/proxy sessions, filter cookies, enforce proxy scope, correct URL joining and status checks, close sessions. |
| `fetch_hal.py` | Route requests and writes through shared protections. |
| `fetch_istex.py` | Route requests and writes through shared protections, including token stripping on cross-origin redirects. |
| `fetch_libgen.py` | Preserve PDF/EPUB selection; apply protected requests/writes and bounded existing-file checks. |
| `fetch_scihub.py` | Preserve Sci-Hub/SciDB/Anna's Archive discovery; enforce successful PDF status and shared bounded writes. |
| `fetch_url.py` | Apply protected requests and atomic validated writes. |
| `pyproject.toml` | Patched dependency floors, soupsieve 2.x bound, Python 3.10 minimum. |
| `uv.lock` | Regenerated with uv; upgrade affected dependencies and remove Python 3.9-only alternatives. |
| `tests/conftest.py` | Isolate home, cookie/token variables, token path and Zotero discovery; prohibit network in offline tests. |
| `tests/test_fetch_ezproxy.py` | Synthetic PDF EOF marker and session-close test double; formatter output. |
| `tests/test_fetch_istex.py` | Synthetic PDF EOF marker. |
| `tests/test_fetch_scihub.py` | Synthetic PDF EOF marker and HTTP-status test double. |
| `tests/test_network.py` | Remove insecure TLS override; use the protected HTTP client and file writer. These real-network tests remain excluded from pytest runs. |
| `tests/test_security.py` | 64 regression cases covering TLS, destinations/DNS pinning, redirects, credentials/cookies, limits, truncation, invalid files and cleanup. |
| `tests/cloud_open_access.py` | Explicit isolated public-download check, request/socket observation, bounded byte-level identity, size and SHA-256; temporary PDF deletion. |
| `.github/workflows/cloud-security.yml` | GitHub-hosted 3.10/3.12 offline checks, universal dependency audit, CodeQL Security Extended and gated opt-in public download. |
| `SECURITY_REVIEW.md` | This report. |

Original CRLF line endings are retained in the affected source files to reduce unrelated diff changes.

## Validation evidence

Baseline [cloud run](https://github.com/morgensternR/DOIfetch/actions/runs/40396159254): **58 offline tests passed**. Its dependency audit reported **23 entries (14 distinct advisory IDs) across seven packages**, including duplicate entries.

Hardened [verification run](https://github.com/morgensternR/DOIfetch/actions/runs/40400459579), code at `cc35c8def05beb5a706a84b66efd6ba8e8bfafd9`:
- **122 offline tests passed on Python 3.10 and 3.12**.
- Tests ran inside disposable containers with `--network none`, no host bind mounts, no forwarded credentials, dropped capabilities, memory/process limits, and a synthetic home.
- `uv run --offline --frozen pytest -q -m "not network" --ignore=tests/test_network.py`.
- Ruff formatting checked for every modified Python file; focused `ruff check --select E4,E7,E9,F` passed. Broader style rules were not used to drive unrelated refactoring.
- Every one of the **28 resolved external package/version entries** in the universal lock was audited, including alternate NumPy/pandas versions and development dependencies. Duplicate package names are audited in separate batches. Both pip-audit batches reported **no known vulnerabilities found**.
- **CodeQL Security Extended completed with zero findings**, scanning all 26 Python files. [SARIF artifact](https://github.com/morgensternR/DOIfetch/actions/runs/40400459579/artifacts/12687538906).
- The first Security Extended run identified an insecure TLS override in the excluded network-test file and a substring match in an EZproxy test double. Both were fixed rather than suppressing the findings; the network tests were not executed.
- The gated public-download check **passed**; details below.

## Dependency findings

| Package | Baseline audited version | Resolved patched version |
| --- | --- | --- |
| certifi | 2026.2.25 | 2026.10.23 |
| idna | 3.11 | 3.20 |
| Pygments | 2.19.2 | 2.21.0 |
| pytest | 9.0.2 (plus 8.4.2 Python alternative) | 9.1.1 |
| Requests | 2.32.5 | 2.34.2 |
| soupsieve | 2.8.3 | 2.10 |
| urllib3 | 2.6.3 | 2.8.0 |

Baseline advisory IDs, as returned by pip-audit: PYSEC-2026-4320, 215, 2987, 1845, 2275, 3072, 3071, 4170, 4171, 141, 142, 4177, 4176, 4175 (all use the PYSEC-2026 prefix). These are scanner findings, not an independent exploit demonstration. Audit results are limited to the advisory service's knowledge at execution time.

## Public download and observed destinations

Crossref returned HTTP 200 metadata but no qualifying PDF link. The separately authorized public PLOS endpoint returned HTTP 200 and a PDF whose DOI was found by bounded Flate-byte inspection.

- DOI: `10.1371/journal.pone.0000001`.
- Crossref title: **Neural Substrate of Cold-Seeking Behavior in Endotoxin Shock**.
- Size: **816,502 bytes**.
- SHA-256: `22f2423f45940809cc040415b5045a707b907fddec6a0c43bea16ac6455c72b0`.
- The literal DOI was confirmed inside bounded decoded bytes. An exact title byte match was not found; the title above comes from Crossref metadata.
- All three observed HTTP requests in the passing run used HTTPS with certificate verification and no Cookie or Authorization header. No redirects occurred in this live run; redirects were exercised by offline regressions.
- The first raw-byte identity check failed, as did a preliminary decoder that required a newline before the PDF stream keyword. Those checker failures required two repeat retrievals of the same public PDF. **All three retrievals had identical size and SHA-256**. The passing checker handles adjacent `>>stream` boundaries; no full PDF parser was introduced.
- PDFs were removed with their temporary directories, including on failed identity checks. Only JSON reports and SARIF results were retained as workflow artifacts.

| Observed destination | Socket destination(s) in the passing run | Purpose |
| --- | --- | --- |
| `api.crossref.org` | `98.95.198.47:443`, `13.223.213.24:443` | DOI lookup and metadata identity cross-check |
| `journals.plos.org` | `35.190.43.188:443` | Public PLOS PDF endpoint |

The earlier retrievals used the same three IP addresses overall.
[Passing download report artifact](https://github.com/morgensternR/DOIfetch/actions/runs/40400459579/artifacts/12688107971).


Only the public DOI `10.1371/journal.pone.0000001` was tested. The optional `10.1016/j.applthermaleng.2022.119951` source-chain attempt was not performed.

The network report records HTTP URLs/statuses and socket connection attempts, not a packet capture. Build/audit/CodeQL provisioning also contacted GitHub, its action/artifact services, Docker Hub, and Python package/advisory services; those setup destinations were not exhaustively packet-logged.

## Remaining limits and risks

- This review does **not** prove the software or downloaded documents safe. Lightweight signatures/EOF markers and a matching DOI do not detect malicious PDF JavaScript, embedded files, malformed internal object graphs, or exploits in a later viewer. No real PDF was opened in a viewer, rendered, executed, or passed to a full PDF parser. Identity checking uses standard-library zlib only: at most 128 candidate Flate streams, 2 MiB decoded per stream and 16 MiB decoded per search.
- Public servers can still be hostile. An intentionally configured proxy domain must be trusted. Public HTTP remains available for compatibility; its content is unauthenticated. The code blocks local destinations but is not a replacement for an independent egress firewall.
- The urllib3 connection override depends on its connection/pool interfaces; future upgrades need these regression tests and a public HTTPS check.
- The size limit bounds response bodies, not total process memory: responses are buffered with bounded intermediate copies, multiplied by concurrent workers. Timeouts are connect/read inactivity limits, not an overall transfer deadline.
- The output directory is assumed to be controlled by the caller. Atomic replacement and symlink refusal do not provide full defense against a malicious local process concurrently replacing parent directories.
- Institutional EZproxy/ISTEX authentication was tested only with synthetic credentials. No live credentialed institutional compatibility test was performed. Cross-domain SSO redirects, private-network proxies, nonstandard ports, ambient netrc/proxy settings and broken certificate chains now fail closed.
- CLI error messages can include publisher-supplied signed download URLs. Treat operational logs as potentially sensitive; this patch does not redesign logging.
- Source availability, anti-bot restrictions, content accuracy and access entitlements were not exhaustively tested. All source code paths remain, but preservation of source support is not a claim that every remote service currently works.
- Existing reference-file update behavior and Zotero auto-detection outside tests remain unchanged. This review did not authorize or perform a real batch run against user reference files.

The workflow runs live downloads only for an explicit `workflow_dispatch` with `open_access=true`, or a push commit whose message contains `[open-access-check]`. Ordinary verification runs do not download papers. CodeQL SARIF is retained as a workflow artifact; it is not uploaded into the fork's existing default-setup code-scanning configuration.

## Full diff

[Review the complete diff against the requested baseline](https://github.com/morgensternR/DOIfetch/compare/881878996e63f633fd91af1f69a19b1b167f7107...security/cloud-hardening).
The report commit changes documentation only; the tested source commit is recorded above.
