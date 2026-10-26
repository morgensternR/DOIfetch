"""Offline memory measurement of the real bounded get(), using synthetic transport."""

import concurrent.futures
import json
import resource
import subprocess
import sys
import threading
from pathlib import Path

import fetch  # Include the normal batch command's imports in the memory baseline.
import safe_http
from requests import Response

MIB = 1024 * 1024


def rss_mib():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("Linux RSS unavailable")


def measure(workers, size_mib, bodies):
    baseline = rss_mib()
    full_chunks = threading.Barrier(workers)
    held = []
    all_responses = threading.Barrier(workers, action=lambda: held.append(rss_mib()))
    size = size_mib * MIB

    def send(request, **kwargs):
        assert kwargs["stream"] is True and kwargs["verify"] is True
        response = Response()
        response.status_code = 200
        response.url = request.url
        response.headers["Content-Length"] = str(size)

        def chunks(chunk_size):
            remaining = size
            while remaining:
                count = min(chunk_size, remaining)
                # Allocate independent chunks, rather than reuse one bytes object.
                yield b"x" * count
                remaining -= count
            full_chunks.wait(timeout=120)

        response.iter_content = chunks
        response.close = lambda: None
        return response

    def worker(_):
        with safe_http.Session() as session:
            session.send = send
            responses = [
                session.get("https://example.org/synthetic", stream=True)
                for _ in range(bodies)
            ]
            all_responses.wait(timeout=120)
            return sum(len(response.content) for response in responses)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        total = sum(executor.map(worker, range(workers)))
    assert total == workers * size * bodies
    return {
        "workers": workers,
        "response_mib": size_mib,
        "retained_bodies_per_worker": bodies,
        "baseline_rss_mib": round(baseline, 2),
        "held_responses_rss_mib": round(max(held), 2),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
        ),
        "retained_payload_mib": total / MIB,
        "configured_limit_bytes": safe_http.max_download_bytes(),
        "configured_workers": fetch.MAX_THREADS,
    }


def main():
    if len(sys.argv) == 4:
        print(json.dumps(measure(*map(int, sys.argv[1:]))))
        return
    cases = [(1, 1, 1), (15, 1, 1), (15, 10, 1), (1, 50, 1), (15, 50, 1), (15, 50, 2)]
    results = []
    for case in cases:
        completed = subprocess.run(
            [sys.executable, __file__, *map(str, case)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        results.append(json.loads(completed.stdout))
    print(
        json.dumps(
            {
                "python": sys.version,
                "cases": results,
                "method": "fresh Linux process per case; real Session.get with synthetic streaming transport; synchronized full chunk buffers and retained responses; no sockets",
                "two_body_case": "models a retained landing/API response while fetching a PDF",
                "limitations": "excludes HTML/JSON object expansion, TLS buffers and OS cache; synthetic synchronized workload is not a production trace",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
