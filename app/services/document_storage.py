import hashlib
import mimetypes
import os
import uuid
from pathlib import Path

from app.config import settings


ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}


def save_original(account_id: str, filename: str, content: bytes) -> tuple[str, str, str]:
    """Atomically stores an original upload under an opaque, account-scoped key."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Unsupported file type. Upload a PDF or text file.")
    account_dir = (settings.UPLOAD_DIR / account_id).resolve()
    upload_root = settings.UPLOAD_DIR.resolve()
    if account_dir != upload_root and upload_root not in account_dir.parents:
        raise ValueError("Invalid account storage path")
    account_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(content).hexdigest()
    mime_type = "application/pdf" if suffix == ".pdf" else mimetypes.guess_type(filename)[0] or "text/plain"
    if settings.STORAGE_BUCKET:
        try:
            from google.cloud import storage
        except ImportError as error:
            raise RuntimeError("STORAGE_BUCKET requires google-cloud-storage") from error
        object_name = f"accounts/{account_id}/documents/{uuid.uuid4().hex}{suffix}"
        storage.Client().bucket(settings.STORAGE_BUCKET).blob(object_name).upload_from_string(content, content_type=mime_type)
        return f"gs://{settings.STORAGE_BUCKET}/{object_name}", content_hash, mime_type
    destination = account_dir / f"{uuid.uuid4().hex}{suffix}"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with open(temporary, "xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination), content_hash, mime_type


def _blob(location: str):
    from google.cloud import storage
    bucket_name, _, object_name = location[5:].partition("/")
    return storage.Client().bucket(bucket_name).blob(object_name)


def read_original(location: str) -> bytes:
    return _blob(location).download_as_bytes() if location.startswith("gs://") else Path(location).read_bytes()


def delete_original(location: str) -> None:
    if location.startswith("gs://"):
        _blob(location).delete()
    else:
        Path(location).unlink(missing_ok=True)


def original_exists(location: str) -> bool:
    return _blob(location).exists() if location.startswith("gs://") else Path(location).is_file()
