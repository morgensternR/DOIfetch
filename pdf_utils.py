"""Lightweight file checks only: never render or execute downloaded documents."""

import os
import re
import tempfile

from safe_http import max_download_bytes


def clean_filename(title):
    """Remove illegal filename characters and truncate."""
    illegal_chars = r'[\\/:*?"<>|]'
    return re.sub(illegal_chars, "", title)[:120]


def is_valid_pdf(file_path):
    """Check size, PDF header and EOF marker; this is not a safety guarantee."""
    try:
        if os.path.islink(file_path):
            return False
        with open(file_path, "rb") as f:
            header = f.read(8)
            if not re.fullmatch(rb"%PDF-[12]\.[0-9]", header):
                return False
            f.seek(0, 2)
            size = f.tell()
            if not 1000 <= size <= max_download_bytes():
                return False
            f.seek(max(0, size - 1024))
            return f.read().rstrip().endswith(b"%%EOF")
    except (OSError, ValueError):
        return False


def write_download(file_path, content, *, epub=False):
    """Validate in a private sibling file, then atomically publish; always clean up."""
    if not 1000 <= len(content) <= max_download_bytes():
        raise ValueError("Download is empty, too small, or exceeds the size limit")
    if os.path.islink(file_path):
        raise ValueError("Refusing a symbolic-link destination")
    fd, temporary = tempfile.mkstemp(
        prefix=".doifetch-",
        suffix=".part",
        dir=os.path.dirname(os.path.abspath(file_path)),
    )
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
        if epub:
            # Bounded signature checks; no archive extraction or decompression.
            valid = (
                content.startswith(b"PK\x03\x04")
                and b"application/epub+zip" in content[:512]
                and b"PK\x05\x06" in content[-65557:]
            )
        else:
            valid = is_valid_pdf(temporary)
        if not valid:
            raise ValueError("Downloaded file has an invalid PDF/EPUB structure")
        os.replace(temporary, file_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
