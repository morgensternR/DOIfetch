# Final cloud verification

Date: 2026-10-26 UTC. Branch: `security/cloud-hardening`.
Starting commit: `7eae2f1a7445ec43dacb2ffc467fce8b70a3a955`.
Verified implementation and workflow: `e6c7c30c0fc5e26b8478ee13145521304cbf8858`.
This report is a documentation-only follow-up to that verification.

All execution used GitHub-hosted runners. No commands, tests, installations, or file access occurred on the user's Windows PC. No merge or deployment was performed. Application sources, source order, security protections, dependencies, and `uv.lock` are unchanged from the starting commit. These checks do not prove the software safe.

## Evidence and reproducibility

[Complete verification run](https://github.com/morgensternR/DOIfetch/actions/runs/40402817909).
[Live and memory job logs](https://github.com/morgensternR/DOIfetch/actions/runs/40402817909/job/121853199945).
[Download raw JSON reports](https://github.com/morgensternR/DOIfetch/actions/runs/40402817909/artifacts/12689359335).
The report artifact contains `source-chain-report.json` and `memory-report.json`; GitHub currently expires it on 2027-01-24. The material outcomes, all provider/mirror results, network destinations, and full connection errors are preserved below.

The live check used a fresh Python 3.12.15 Linux container built from tracked repository files, without a Git directory, host bind mounts, forwarded environment variables, personal files, or institutional credentials. Its HOME was an empty disposable directory. The harness disabled token-file reads and Zotero discovery, passed `zotero_db=None`, and asserted that credential variables were absent. The container had dropped capabilities, no-new-privileges, PID and memory limits, and was removed after the run. No PDF viewer, executable, full PDF parser, or external document converter ran.

Image ID: `sha256:6f1612e72e15f5e99b713ae3e2e1459548efa2b223d4ab97fe1f5f24c6740a5e`.
The image tag `python:3.12-slim` can change in future; the observed Python version and image identity above describe this run. Dependencies were installed using `uv==0.13.5` and the committed lockfile.

To repeat in GitHub, dispatch **Cloud security verification** on this branch with `final_cloud=true`. Static tests must pass before the explicitly requested live check runs. Ordinary pushes do not repeat the live download. The memory check uses a separate fresh container with networking disabled. Tests and helpers use `uv run`; both new Python helpers were formatted and linted inside cloud containers before their commits.

## Offline Windows and Linux results

Command:

```text
uv run --offline --frozen pytest -q -m "not network" --ignore=tests/test_network.py
```

| GitHub-hosted environment | Python actually used | Result | Test time |
|---|---|---|---|
| Windows Server 2022 x64 | 3.12.10 | 122 passed, 0 skipped, 0 failed | 5.37 s |
| Windows Server 2025 x64 | 3.12.10 | 122 passed, 0 skipped, 0 failed | 3.13 s |
| Ubuntu 24.04 / disposable Linux container | 3.10.22 | 122 passed | 0.95 s |
| Ubuntu 24.04 / disposable Linux container | 3.12.15 | 122 passed | 1.01 s |

[Windows 2022 logs](https://github.com/morgensternR/DOIfetch/actions/runs/40402817909/job/121852836947);
[Windows 2025 logs](https://github.com/morgensternR/DOIfetch/actions/runs/40402817909/job/121852837388).

The Windows matrix isolates HOME/USERPROFILE, removes institutional and Zotero configuration, and blocks outbound traffic from the test Python executable with Windows Firewall. The existing pytest fixture additionally rejects socket connections and isolates token/reference paths. Linux offline tests run with Docker networking disabled. Windows JUnit results are retained as workflow artifacts.

File handling coverage includes malformed-file rejection while preserving an existing destination, atomic-replacement failure cleanup, oversized-file rejection, symlink rejection, and provider failure cleanup. All existing 122 tests passed on Windows without changes to application or test logic. This is coverage of the tested operations, not every Windows filesystem, network share, antivirus interaction, or long-path configuration.

Ruff formatting and focused lint checks passed. The universal lockfile dependency audit reported **no known vulnerabilities** in either audit batch (28 external package/version entries, including conditional versions). CodeQL **Security Extended returned zero findings**. These checks do not audit every operating-system component or the Python interpreter; note the different Windows and Linux Python patch versions.

## DOI source-chain result

Requested and Crossref-resolved DOI: **10.1016/j.applthermaleng.2022.119951**.

Crossref title: **Theoretical and experimental investigations on the supercritical startup of a cryogenic axially Ω-shaped grooved heat pipe**.

Crossref metadata supplied the normal reference label `Li 2023 - <title>`, allowing the existing HAL author/title search to run. The DOI contains 2022, while the metadata publication year is 2023; the harness used the metadata year rather than inferring it from the DOI.

The unchanged call was `fetch._fetch_one(DOI, label, output, "all", zotero_db=None)`. Observer wrappers recorded HTTP attempts, exceptions, redirects, mirror extraction results, provider results, and socket destinations. No provider order, matching algorithm, TLS behavior, or download limit was changed.

| Provider, in normal order | Observed result |
|---|---|
| Crossref | API HTTP 200; `No open access PDF found in Crossref`. This means no link matching the fetcher's existing PDF/version-of-record selection, not proof that no public copy exists anywhere. |
| Unpaywall | API HTTP 200; `No open access PDF found`. |
| HAL | Search HTTP 200; `No PDF found on HAL`. |
| ISTEX | Failed fast: `ISTEX_ACCESSTOKEN not set (generate at https://api.istex.fr/token/)`. No token file read or network request. |
| EZproxy | Failed fast: `EZPROXY_BASE not set (your institution's EZproxy host suffix)`. No cookie file read or network request. |
| Sci-Hub, then SciDB / Anna's Archive | All 13 configured mirrors attempted; none produced an accepted PDF. Details below. |
| LibGen | Not attempted: the existing router invokes it for ISBNs, not this DOI. Support is unchanged. |

All six DOI providers were attempted. The chain returned `failed`; the disposable output directory was empty afterward. A missing paper is **not a security-test failure**.

**No PDF was downloaded successfully. PDF size, SHA-256, retrieval source, and correct-paper identity are therefore unavailable.** The resolved DOI and title above are metadata verification only. The harness would require a valid lightweight PDF structure plus **both** the DOI and exact Crossref title in bounded raw-byte/Flate inspection before reporting a successful download as identity-verified. That conditional path was not exercised in this run.

### Every Sci-Hub / SciDB mirror

| Mirror | Result |
|---|---|
| `sci-hub.fr` | HTTP 200, 610 bytes; first iframe resolved to `https://acceptable.a-ads.com/2425588/?size=Adaptive`. That candidate returned HTTP 200, 23,094 bytes, but was not accepted as a PDF; the loop continued. |
| `sci-hub.hkvisa.net` | HTTP 403; no PDF link extracted. |
| `sci-hub.ru` | HTTP 200; no PDF link extracted. |
| `sci-hub.st` | HTTP 200; no PDF link extracted. |
| `sci-hub.se` | ConnectionError / `Public connection failed`; no socket address recorded. |
| `sci-hub.ren` | HTTP 200; no PDF link extracted. |
| `sci-hub.tw` | ConnectionError / `Public connection failed`; attempted `104.247.81.99:443`. |
| `sci-hub.ee` | HTTP 200; no PDF link extracted. |
| `sci-hub.shop` | HTTP 200; no PDF link extracted. |
| `sci-hub.la` | ConnectionError / `Public connection failed`; attempted `104.247.81.99:443`. |
| `annas-archive.se` | ConnectionError / `Public connection failed`; no socket address recorded. |
| `annas-archive.org` | ConnectionError / `Public connection failed`; no socket address recorded. |
| `annas-archive.gd` | HTTPS 308 → 302 → 403 on the same host; no PDF link extracted. |

The `.gd` redirects added a trailing slash and then `?&check=1`. Two redirected requests carried cookies issued by that anonymous public session. There were no supplied browser/institutional cookies, credentials, or Authorization headers. Cookie values were neither logged nor preserved.

The Sci-Hub loop retains only its last failure in its final result. The observer preserves HTTP/mirror events, but the earlier ad-candidate validation exception's exact text was swallowed by the existing loop; its rejection is inferred from the unchanged control flow continuing to the next mirror. No error text is invented here. The final provider error was `PDF link not found` at `https://annas-archive.gd/scidb/10.1016/j.applthermaleng.2022.119951`.

Full recorded connection errors:

```text
ConnectionError: _HTTPSPool(host='sci-hub.se', port=443): Max retries exceeded with url: /10.1016/j.applthermaleng.2022.119951 (Caused by NewConnectionError("_HTTPSConnection(host='sci-hub.se', port=443): Public connection failed"))

ConnectionError: _HTTPSPool(host='sci-hub.tw', port=443): Max retries exceeded with url: /10.1016/j.applthermaleng.2022.119951 (Caused by NewConnectionError("_HTTPSConnection(host='sci-hub.tw', port=443): Public connection failed"))

ConnectionError: _HTTPSPool(host='sci-hub.la', port=443): Max retries exceeded with url: /10.1016/j.applthermaleng.2022.119951 (Caused by NewConnectionError("_HTTPSConnection(host='sci-hub.la', port=443): Public connection failed"))

ConnectionError: _HTTPSPool(host='annas-archive.se', port=443): Max retries exceeded with url: /scidb/10.1016/j.applthermaleng.2022.119951 (Caused by NewConnectionError("_HTTPSConnection(host='annas-archive.se', port=443): Public connection failed"))

ConnectionError: _HTTPSPool(host='annas-archive.org', port=443): Max retries exceeded with url: /scidb/10.1016/j.applthermaleng.2022.119951 (Caused by NewConnectionError("_HTTPSConnection(host='annas-archive.org', port=443): Public connection failed"))
```

These generic errors do not establish whether a failure arose from DNS, destination policy, or connect failure. No insecure TLS retry was attempted.

## Observed network destinations

There were 20 prepared HTTPS request attempts, including metadata resolution, redirects, and attempts that failed before connection. All requested verified TLS. No Authorization header was sent. Socket audit events record **connection attempts**, not proof that each connection succeeded.

| Requested host | Socket destination(s), all port 443 | HTTP result(s) |
|---|---|---|
| `api.crossref.org` | `100.27.84.37:443` | 200 |
| `api.unpaywall.org` | `35.71.145.101:443` | 200 |
| `api.archives-ouvertes.fr` | `193.48.96.35:443` | 200 |
| `sci-hub.fr` | `186.2.165.17:443` | 200 |
| `acceptable.a-ads.com` | `78.46.33.196:443` | 200 |
| `sci-hub.hkvisa.net` | `104.21.59.231:443` | 403 |
| `sci-hub.ru` | `190.115.31.218:443` | 200 |
| `sci-hub.st` | `186.2.163.201:443` | 200 |
| `sci-hub.se` | No socket address recorded | ConnectionError |
| `sci-hub.ren` | `172.67.168.135:443` | 200 |
| `sci-hub.tw` | `104.247.81.99:443` | ConnectionError |
| `sci-hub.ee` | `172.67.212.102:443` | 200 |
| `sci-hub.shop` | `172.67.161.98:443` | 200 |
| `sci-hub.la` | `104.247.81.99:443` | ConnectionError |
| `annas-archive.se` | No socket address recorded | ConnectionError |
| `annas-archive.org` | No socket address recorded | ConnectionError |
| `annas-archive.gd` | `186.2.165.77:443` | 308 → 302 → 403 |

No private/local socket destination was observed. DNS resolver traffic is not captured by this Python socket-connect log. Package installation, GitHub Actions control traffic, and the separate dependency audit are outside this live-request trace.

## Memory review and measurement

`safe_http.Session.get()` consumes decoded response chunks into a list, then creates `b"".join(chunks)`. The `stream=True` argument does not make the returned body stream to disk. At the join, a response can temporarily occupy roughly twice its body size. Returning frees the chunk-list references, but Python/libc can retain allocated memory in RSS.

At 50 MiB per response and 15 active workers, retained PDF bodies alone total **750 MiB**. Conservative simultaneous chunk/join storage is about **1,500 MiB**, before interpreter imports, transport buffers, allocator retention, or retained API/landing responses. Existing fetchers can keep a landing/API response alive while downloading a PDF, adding another body per worker. The per-response byte cap is not a process-memory cap.

The offline benchmark used the real `Session.get()` with a synthetic transport yielding independently allocated 64 KiB chunks. Worker barriers synchronized full chunk buffers and retained response bodies. Each case ran in a fresh process with normal `fetch` imports, under Linux CPython 3.12.15. No sockets or PDFs were involved.

| Workers | MiB per response | Retained responses per worker | Baseline RSS MiB | RSS with responses held, MiB | Peak RSS MiB |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 79.86 | 81.89 | 89.33 |
| 15 | 1 | 1 | 80.09 | 110.51 | 110.16 |
| 15 | 10 | 1 | 79.96 | 352.05 | 369.02 |
| 1 | 50 | 1 | 79.8 | 136.77 | 179.8 |
| 15 | 50 | 1 | 79.67 | 951.77 | 1212.47 |
| 15 | 50 | 2 | 79.68 | 1701.83 | 2016.61 |

Observed peak for fifteen 10 MiB responses: **369 MiB**. For fifteen 50 MiB responses: **1,212 MiB (1.18 GiB)**. With an additional 50 MiB retained response per worker: **2,017 MiB (1.97 GiB)**. A preparatory run of the same two-body case peaked at **2,063 MiB (2.01 GiB)**, illustrating scheduling/allocator variability.

Practical planning estimates for this implementation:

- For approximately 1–10 MiB papers at 15 workers, allow roughly **0.5–1 GiB** for ordinary batches, depending on metadata and HTML processing.
- For frequent downloads near the 50 MiB cap, allow roughly **2 GiB** for predominantly PDF buffering; this has limited headroom.
- For near-limit landing/API responses retained alongside PDFs, a **3–4 GiB** process allowance is more realistic than 2 GiB.

These are measured-workload planning estimates, **not upper bounds**. JSON decoding, Unicode text, and BeautifulSoup trees may expand well beyond wire/body sizes; malicious or unusually complex HTML can exceed those allowances. Windows allocators may differ. TLS/socket buffers, OS page cache, unrelated applications, and larger reference tables add costs. An external process/container memory limit remains useful; this verification used 4 GiB for the benchmark and 2 GiB for the single-DOI live check. No refactor was made because the existing bounded-download behavior was retained and the measured limitations can be stated directly.

## New findings and remaining limits

1. **Unrelated public iframe requests:** `extract_pdf_url()` accepts the first iframe/embed. The real Sci-Hub page led to an advertising URL. The candidate was not accepted as a PDF and no partial file remained, but SSRF protections intentionally allow public HTTP(S) destinations, so they do not prevent this unwanted public-site request. Link selection remains unchanged to preserve source behavior.
2. **Batch memory pressure:** the response limit does not bound total process memory. Fifteen workers can exceed a 2 GiB budget when multiple large responses are retained; parsed HTML/JSON can increase this further.
3. **Limited failure diagnostics:** the Sci-Hub loop overwrites earlier failures, and the connection layer wraps distinct connection causes in a generic error. The harness captures observed HTTP errors without guessing missing causes.
4. **Correct-paper validation is still conditional:** the production downloader's lightweight structural validation does not prove paper identity or PDF safety. This run obtained no PDF, so it cannot establish successful retrieval or identity for this DOI.
5. Network/provider availability is time-dependent; anonymous access failures do not imply a source was removed or that credentialed access is broken. Institutional authentication was intentionally not exercised.

## Files changed from the requested starting commit

| File | Purpose |
|---|---|
| `.github/workflows/cloud-security.yml` | Hosted Windows 2022/2025 Python 3.12 matrix; offline firewall isolation; JUnit artifacts; opt-in isolated memory/source-chain verification after static checks; lint checks for helpers. |
| `tests/cloud_final_verification.py` | Explicit cloud-only DOI chain observer, personal-file safeguards, temporary output cleanup, and conditional DOI/title identity checks. Not collected as a pytest test. |
| `tests/cloud_memory.py` | Explicit Linux cloud memory benchmark using the real buffering routine and a synthetic offline transport. Not collected as a pytest test. |
| `CLOUD_VERIFICATION.md` | This report. |

A temporary formatting workflow was removed after it produced the cloud-formatted helper commits. It is absent from the final tree. The application files and dependency lockfile have no diff from the requested starting commit.
