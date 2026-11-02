"""Document upload/view/delete: professional KYC files and patient prescriptions, with the
bucket replaced by an in-memory fake (no network, no real storage)."""

import uuid

import pytest
from sqlalchemy import update

from app.core.constants import UserRole
from app.db.session import AsyncSessionLocal
from app.models.service import Service
from app.services import storage_service
from tests.conftest import set_config
from tests.integration.test_booking_flow import (
    INDIRANAGAR,
    _data,
    _next_ist,
    _nurse,
    _patient_with_address,
    _register,
)
from tests.integration.test_premium_rules import _set_user

pytestmark = pytest.mark.asyncio
PDF = {"content_type": "application/pdf", "size_bytes": 120_000}


class FakeS3:
    objects: dict[str, dict] = {}

    def presign_upload(self, key, *, content_type):
        return f"https://bucket.test/{key}?sig=put"

    def presign_download(self, key):
        return f"https://bucket.test/{key}?sig=get"

    def head(self, key):
        return self.objects.get(key)

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture(autouse=True)
def fake_bucket(monkeypatch):
    FakeS3.objects = {}
    monkeypatch.setattr(storage_service, "S3Client", FakeS3)
    return FakeS3.objects


async def _upload(client, headers, base: str, body: dict | None = None) -> str:
    """Get an upload URL, then simulate the app's PUT by putting the object in the fake."""
    out = _data(await client.post(f"{base}/upload-url", headers=headers, json=body or PDF))
    assert out["method"] == "PUT" and out["headers"] == {"Content-Type": "application/pdf"}
    FakeS3.objects[out["file_key"]] = {"content_type": "application/pdf", "size": 120_000}
    return out["file_key"]


async def test_professional_uploads_lists_and_deletes_kyc_documents(client, fake_bucket):
    nurse = await _nurse(client, "Doc Nurse", INDIRANAGAR)
    base = "/api/v1/professionals/me/documents"

    bad_type = await client.post(
        f"{base}/upload-url", headers=nurse, json={"content_type": "text/html", "size_bytes": 10}
    )
    assert bad_type.json()["error"]["code"] == "unsupported_file_type"
    too_big = await client.post(
        f"{base}/upload-url",
        headers=nurse,
        json={"content_type": "image/jpeg", "size_bytes": 50 * 1024 * 1024},
    )
    assert too_big.json()["error"]["code"] == "file_too_large"

    key = await _upload(client, nurse, base)
    assert key.startswith("kyc/")
    not_uploaded = await client.post(
        base,
        headers=nurse,
        json={"document_type": "government_id", "file_key": key.replace(".pdf", "-x.pdf")},
    )
    assert not_uploaded.json()["error"]["code"] == "upload_missing"

    doc = _data(
        await client.post(
            base, headers=nurse, json={"document_type": "government_id", "file_key": key}
        )
    )
    assert doc["verification_status"] == "pending"
    assert doc["view_url"].startswith("https://bucket.test/kyc/")
    assert doc["content_type"] == "application/pdf"

    # Re-uploading the same type replaces the pending one (and its file).
    key2 = await _upload(client, nurse, base)
    _data(
        await client.post(
            base, headers=nurse, json={"document_type": "government_id", "file_key": key2}
        )
    )
    listed = _data(await client.get(base, headers=nurse))
    assert [d["document_type"] for d in listed] == ["government_id"]
    assert key not in fake_bucket and key2 in fake_bucket

    # Someone else's key can't be claimed.
    other = await _nurse(client, "Other Nurse", INDIRANAGAR)
    stolen = await client.post(
        base, headers=other, json={"document_type": "government_id", "file_key": key2}
    )
    assert stolen.json()["error"]["code"] == "invalid_file_key"

    deleted = await client.delete(f"{base}/{listed[0]['id']}", headers=nurse)
    assert deleted.status_code == 200
    assert _data(await client.get(base, headers=nurse)) == []
    assert key2 not in fake_bucket


async def test_admin_reviews_documents_and_verified_ones_are_locked(client):
    nurse = await _nurse(client, "Review Nurse", INDIRANAGAR)
    admin = await _register(client, "patient", "Doc Admin")
    await _set_user(admin, role=UserRole.SUPER_ADMIN)
    base = "/api/v1/professionals/me/documents"
    for doc_type in ("government_id", "nursing_council_certificate"):
        key = await _upload(client, nurse, base)
        _data(
            await client.post(
                base, headers=nurse, json={"document_type": doc_type, "file_key": key}
            )
        )
    me = _data(await client.get("/api/v1/professionals/me", headers=nurse))
    docs = {d["document_type"]: d for d in _data(await client.get(base, headers=nurse))}

    detail_url = f"/api/v1/admin/professionals/{me['id']}"
    detail = _data(await client.get(detail_url, headers=admin))
    assert all(d["view_url"].startswith("https://bucket.test/") for d in detail["documents"])

    cert = docs["nursing_council_certificate"]["id"]
    rejected = _data(
        await client.post(
            f"{detail_url}/documents/{cert}/review",
            headers=admin,
            json={"decision": "rejected", "rejection_reason": "Certificate is blurry"},
        )
    )
    cert_row = next(d for d in rejected["documents"] if d["id"] == cert)
    assert cert_row["verification_status"] == "rejected"
    inbox = _data(await client.get("/api/v1/notifications", headers=nurse))
    assert inbox["items"][0]["title"] == "Please re-upload a document"

    gov = docs["government_id"]["id"]
    _data(
        await client.post(
            f"{detail_url}/documents/{gov}/review", headers=admin, json={"decision": "approved"}
        )
    )
    locked = await client.delete(f"{base}/{gov}", headers=nurse)
    assert locked.status_code == 409
    # An admin can still remove it.
    after = _data(await client.delete(f"{detail_url}/documents/{gov}", headers=admin))
    assert gov not in {d["id"] for d in after["documents"]}


async def test_prescription_is_shared_only_while_the_visit_is_live(client, nursing_service_id):
    await set_config("verification", {"auto_approve": True})
    await set_config("app.features", {"prescription_upload": True})
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Service)
            .where(Service.id == uuid.UUID(nursing_service_id))
            .values(requires_prescription=True)
        )
        await session.commit()
    try:
        patient, address_id = await _patient_with_address(client)
        nurse = await _nurse(client, "Rx Nurse", INDIRANAGAR)
        booking_body = {
            "service_id": nursing_service_id,
            "address_id": address_id,
            "scheduled_start_at": _next_ist(5, 16).isoformat(),
        }

        missing = await client.post("/api/v1/bookings", headers=patient, json=booking_body)
        assert missing.json()["error"]["code"] == "prescription_required"

        base = "/api/v1/medical-documents"
        key = await _upload(client, patient, base)
        assert key.startswith("medical/")
        rx = _data(
            await client.post(
                base,
                headers=patient,
                json={"document_type": "prescription", "file_key": key, "title": "Dr. Rao"},
            )
        )
        booking = _data(
            await client.post(
                "/api/v1/bookings",
                headers=patient,
                json={**booking_body, "document_ids": [rx["id"]]},
            )
        )
        assert [d["id"] for d in booking["documents"]] == [rx["id"]]

        requests = _data(await client.get("/api/v1/bookings/professional/requests", headers=nurse))
        request = next(r for r in requests if r["id"] == booking["id"])
        assert request["has_documents"] is True and "documents" not in request

        accepted = _data(
            await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=nurse)
        )
        assert [d["id"] for d in accepted["documents"]] == [rx["id"]]

        # Another patient can't touch it.
        stranger = await _register(client, "patient", "Stranger")
        assert (await client.delete(f"{base}/{rx['id']}", headers=stranger)).status_code == 404

        _data(
            await client.post(
                f"/api/v1/bookings/{booking['id']}/cancel",
                headers=patient,
                json={"reason": "Other"},
            )
        )
        after_cancel = _data(
            await client.get(f"/api/v1/bookings/professional/{booking['id']}", headers=nurse)
        )
        assert after_cancel["documents"] == []

        assert (await client.delete(f"{base}/{rx['id']}", headers=patient)).status_code == 200
        assert key not in FakeS3.objects
        assert _data(await client.get(base, headers=patient)) == []
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Service)
                .where(Service.id == uuid.UUID(nursing_service_id))
                .values(requires_prescription=False)
            )
            await session.commit()
        await set_config("app.features", {})
        await set_config("verification", {"auto_approve": False})
