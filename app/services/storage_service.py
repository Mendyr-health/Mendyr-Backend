"""Upload/view/delete for private files: professional KYC documents, patient prescriptions
and reports. Bytes never hit our API — the app PUTs straight to the bucket with a presigned
URL, then records the object key with us, and every view is a fresh short-lived link.

Object keys are random (`<folder>/<uuid>.<ext>`) and namespaced per owner, so a key can be
checked against its owner when it's recorded, and nothing identifying is in the name.
"""

import uuid

from app.core.config import settings
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.integrations.s3_client import S3Client

logger = get_logger(__name__)

# What can be uploaded: scans/photos and PDFs.
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


def kyc_folder(professional_id: uuid.UUID) -> str:
    return f"kyc/{professional_id}"


def medical_folder(user_id: uuid.UUID) -> str:
    return f"medical/{user_id}"


class StorageService:
    def __init__(self) -> None:
        self.s3 = S3Client()

    def presign_upload(self, *, folder: str, content_type: str, size_bytes: int) -> dict:
        content_type = content_type.lower().strip()
        ext = ALLOWED_CONTENT_TYPES.get(content_type)
        if ext is None:
            raise ValidationAppError(
                "Upload a PDF or a photo (JPG, PNG, WEBP or HEIC).", code="unsupported_file_type"
            )
        if size_bytes <= 0 or size_bytes > settings.UPLOAD_MAX_BYTES:
            raise ValidationAppError(
                f"Files can be up to {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
                code="file_too_large",
            )
        key = f"{folder}/{uuid.uuid4()}.{ext}"
        return {
            "upload_url": self.s3.presign_upload(key, content_type=content_type),
            "file_key": key,
            "method": "PUT",
            # The PUT must carry exactly this header, or the signature won't match.
            "headers": {"Content-Type": content_type},
            "expires_in": settings.PRESIGNED_URL_TTL_SECONDS,
        }

    def verify_upload(self, file_key: str, *, folder: str) -> dict:
        """Check an uploaded object is the caller's and within limits before recording it.
        Returns {content_type, size}. An oversized or foreign object is rejected (and an
        oversized one deleted)."""
        if not file_key.startswith(f"{folder}/") or ".." in file_key:
            raise ValidationAppError("That file doesn't belong to you.", code="invalid_file_key")
        meta = self.s3.head(file_key)
        if meta is None:
            raise ValidationAppError(
                "We couldn't find the uploaded file — please upload it again.",
                code="upload_missing",
            )
        if meta["size"] > settings.UPLOAD_MAX_BYTES:
            self.delete(file_key)
            raise ValidationAppError("That file is too large.", code="file_too_large")
        return meta

    def view_url(self, file_key: str) -> str:
        return self.s3.presign_download(file_key)

    def delete(self, file_key: str) -> None:
        """Best-effort: a failed delete leaves an orphaned object, not a broken request."""
        try:
            self.s3.delete(file_key)
        except Exception:  # noqa: BLE001 — storage outage shouldn't fail the user's action
            logger.warning("storage.delete_failed", key=file_key)
