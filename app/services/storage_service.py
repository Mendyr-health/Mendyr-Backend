"""Presigned upload/download URLs for KYC docs and visit proof photos — bytes never hit our API."""

from app.integrations.s3_client import S3Client


class StorageService:
    def __init__(self) -> None:
        self.s3 = S3Client()

    def presign_kyc_upload(self, *, professional_id: str, filename: str, content_type: str) -> dict:
        key = self.s3.build_object_key(folder=f"kyc/{professional_id}", filename=filename)
        return {
            "upload_url": self.s3.presign_upload(key, content_type=content_type),
            "file_url": key,
        }

    def presign_visit_photo_upload(
        self, *, booking_id: str, filename: str, content_type: str
    ) -> dict:
        key = self.s3.build_object_key(folder=f"visits/{booking_id}", filename=filename)
        return {
            "upload_url": self.s3.presign_upload(key, content_type=content_type),
            "file_url": key,
        }

    def presign_download(self, object_key: str) -> str:
        return self.s3.presign_download(object_key)
