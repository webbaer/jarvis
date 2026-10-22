"""Upload handling: sanitize names, enforce size limits, check content, store safely.

Uploaded files are only ever read by the loaders; nothing is executed.
"""
from __future__ import annotations

import os
import re
import shutil
import unicodedata
import uuid
from email.parser import BytesHeaderParser
from pathlib import Path

from fastapi import UploadFile

from jarvis_memory.config import UploadConfig

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_BINARY_MAGIC = (b"%PDF-", b"PK\x03\x04", b"\x7fELF", b"MZ", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")
_EMAIL_HEADERS = ("from", "to", "subject", "date", "message-id")
_FILE_MODE = 0o600


class UploadRejected(Exception):
    """Raised with a user-facing reason when an upload is not accepted."""


def sanitize_filename(raw_name: str | None, max_chars: int) -> str:
    # Drop any directory part (also Windows-style), normalize to ASCII, keep a safe charset.
    name = (raw_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _SAFE_CHARS.sub("_", name).strip("._")
    if not name:
        name = "upload"
    stem, dot, ext = name.rpartition(".")
    if dot and len(name) > max_chars:
        name = stem[: max_chars - len(ext) - 1] + "." + ext
    return name[:max_chars]


def check_extension(name: str, config: UploadConfig) -> str:
    ext = Path(name).suffix.lower()
    if ext not in config.allowed_extensions:
        allowed = ", ".join(config.allowed_extensions)
        raise UploadRejected(f"Dateityp '{ext or 'ohne Endung'}' nicht erlaubt (erlaubt: {allowed})")
    return ext


def check_content(ext: str, data: bytes) -> None:
    """Verify the bytes actually look like the claimed type."""
    if not data:
        raise UploadRejected("Datei ist leer")

    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejected("Inhalt ist kein PDF (Signatur %PDF- fehlt)")
        return

    if data.startswith(_BINARY_MAGIC) or b"\x00" in data:
        raise UploadRejected("Binaerer Inhalt in einer Textdatei")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadRejected("Datei ist kein gueltiger UTF-8-Text") from exc

    if ext == ".eml":
        headers = BytesHeaderParser().parsebytes(data)
        if not any(headers.get(h) for h in _EMAIL_HEADERS):
            raise UploadRejected("Keine E-Mail-Header gefunden (From/To/Subject/Date)")


async def store_upload(upload: UploadFile, uploads_dir: Path, config: UploadConfig) -> Path:
    """Validate and write an upload to its own directory below uploads_dir.

    Raises UploadRejected; nothing is left on disk in that case.
    """
    name = sanitize_filename(upload.filename, config.max_filename_chars)
    ext = check_extension(name, config)

    target_dir = uploads_dir / uuid.uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=False)
    target = target_dir / name
    try:
        size = 0
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
        with os.fdopen(fd, "wb") as out:
            while chunk := await upload.read(config.write_chunk_bytes):
                size += len(chunk)
                if size > config.max_file_bytes:
                    limit_mb = config.max_file_bytes / (1024 * 1024)
                    raise UploadRejected(f"Datei ist groesser als {limit_mb:g} MB")
                out.write(chunk)
        check_content(ext, target.read_bytes())
    except BaseException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    return target
