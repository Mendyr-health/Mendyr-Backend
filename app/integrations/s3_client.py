"""S3-compatible object storage (AWS S3, Filebase, R2…) — KYC documents, prescriptions,
visit proof photos. Uses presigned URLs end-to-end: the apps upload directly to the bucket
and view files through short-lived links, so file bytes never transit the API server.
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class S3Client:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.S3_ADDRESSING_STYLE},
            ),
        )

    def presign_upload(self, object_key: str, *, content_type: str) -> str:
        """A PUT URL. The uploader must send the same Content-Type header."""
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": object_key, "ContentType": content_type},
            ExpiresIn=settings.PRESIGNED_URL_TTL_SECONDS,
        )

    def presign_download(self, object_key: str) -> str:
        """A short-lived GET URL that opens inline (browser PDF/image viewer)."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": object_key,
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=settings.DOWNLOAD_URL_TTL_SECONDS,
        )

    def head(self, object_key: str) -> dict | None:
        """{content_type, size} of an uploaded object, or None if it isn't there."""
        try:
            meta = self._client.head_object(Bucket=settings.S3_BUCKET, Key=object_key)
        except ClientError:
            return None
        return {"content_type": meta.get("ContentType"), "size": meta.get("ContentLength", 0)}

    def delete(self, object_key: str) -> None:
        self._client.delete_object(Bucket=settings.S3_BUCKET, Key=object_key)
