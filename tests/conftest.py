from pathlib import Path
import sys

import pandas as pd
import pytest


from utils import write_table

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_DOIS = [
    ("10.1371/journal.pone.0001636", "Dunbar 2008 - Cognitive Constraints"),
    ("10.1038/d41586-019-02918-5", "Tollefson 2019 - Tracking Emissions"),
]


@pytest.fixture()
def sample_data_dir(tmp_path):
    """Create data dir with 2 DOIs in 3 formats: csv, xlsx, txt."""
    data_dir = tmp_path / "references"
    data_dir.mkdir()

    df = pd.DataFrame(
        [{"DOI": doi, "Article Title": title} for doi, title in SAMPLE_DOIS]
    )

    # CSV
    write_table(df, str(data_dir / "refs.csv"))

    # XLSX
    write_table(df, str(data_dir / "refs.xlsx"))

    # TXT
    lines = [f"doi:{doi}\t{title}" for doi, title in SAMPLE_DOIS]
    (data_dir / "refs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return data_dir


@pytest.fixture(autouse=True)
def isolate_personal_state(monkeypatch, tmp_path, request):
    """Only synthetic test homes, cookies, tokens and Zotero databases are used."""
    import fetch_istex
    import zotero

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for key in (
        "EZPROXY_BASE",
        "EZPROXY_COOKIES",
        "ISTEX_ACCESSTOKEN",
        "ZOTERO_DB_PATH",
        "ZOTERO_DATA_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(zotero, "_HOME", tmp_path)
    monkeypatch.setattr(fetch_istex, "TOKEN_FILE", str(tmp_path / "absent.env"))
    if request.node.get_closest_marker("network") is None:
        import socket

        def no_network(*args, **kwargs):
            raise AssertionError("Offline test attempted network access")

        monkeypatch.setattr(socket, "getaddrinfo", no_network)
        monkeypatch.setattr(socket.socket, "connect", no_network)
