"""S3-compatible object storage — KYC documents, visit proof photos, chat attachments.

Uses presigned URLs end-to-end: the mobile app uploads directly to S3 and downloads
directly from S3, so file bytes never transit the API server.
"""

import uuid

import boto3
from botocore.config import Config

from app.core.config import settings


class S3Client:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            config=Config(signature_version="s3v4"),
        )

    def build_object_key(self, *, folder: str, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        return f"{folder}/{uuid.uuid4()}.{ext}"

    def presign_upload(self, object_key: str, *, content_type: str) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": object_key, "ContentType": content_type},
            ExpiresIn=settings.PRESIGNED_URL_TTL_SECONDS,
        )

    def presign_download(self, object_key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": object_key},
            ExpiresIn=settings.PRESIGNED_URL_TTL_SECONDS,
        )

    def public_url(self, object_key: str) -> str:
        return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{object_key}"
