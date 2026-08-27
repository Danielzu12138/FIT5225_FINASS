from __future__ import annotations

import importlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.common.contracts.models import UploadReservationRequest
from backend.common.errors.models import ApiError
from backend.common.providers.fakes import (
    DeterministicObjectUrlSigner,
    FixedClock,
    InMemoryMediaRepository,
    SequenceIdGenerator,
)
from backend.common.providers.interfaces import ReservationResult


MEDIA_ID = UUID("11111111-1111-4111-8111-111111111111")
DISCARDED_DUPLICATE_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)


def uploads_module():
    return importlib.import_module("backend.aws_api.uploads.service")


def request(**changes: object) -> UploadReservationRequest:
    values: dict[str, object] = {
        "file_name": "Camera Trap.JPG",
        "media_type": "image",
        "size_bytes": 512,
        "sha256": "a" * 64,
    }
    values.update(changes)
    return UploadReservationRequest.model_validate(values)


def service(repository: InMemoryMediaRepository | None = None):
    return uploads_module().UploadReservationService(
        repository=repository or InMemoryMediaRepository(),
        url_signer=DeterministicObjectUrlSigner(
            upload_base_url="https://uploads.example.test",
            download_base_url="https://downloads.example.test",
        ),
        clock=FixedClock(NOW),
        ids=SequenceIdGenerator([MEDIA_ID, DISCARDED_DUPLICATE_ID]),
        bucket_name="pba-media",
        max_size_bytes=1024,
    )


def test_new_reservation_uses_safe_deterministic_key_and_duplicate_has_no_url() -> None:
    repository = InMemoryMediaRepository()
    reservations = service(repository)

    first = reservations.reserve("owner-123", request())
    duplicate = reservations.reserve("owner-123", request())

    expected_key = f"originals/{MEDIA_ID}/{'a' * 64}/camera-trap.jpg"
    assert first.model_dump(mode="json") == {
        "media_id": str(MEDIA_ID),
        "duplicate": False,
        "status": "reserved",
        "upload_url": f"https://uploads.example.test/{expected_key}",
        "object_key": expected_key,
        "expires_in_seconds": 900,
        "upload_headers": {
            "Content-Type": "image/jpeg",
            "x-amz-meta-sha256": "a" * 64,
        },
    }
    assert duplicate.model_dump(mode="json") == {
        "media_id": str(MEDIA_ID),
        "duplicate": True,
        "status": "reserved",
        "upload_url": None,
        "object_key": None,
        "expires_in_seconds": None,
        "upload_headers": None,
    }

    record = repository.get("owner-123", MEDIA_ID)
    assert record is not None
    assert str(record.original_storage_uri) == f"s3://pba-media/{expected_key}"
    assert record.file_name == "camera-trap.jpg"


def test_same_content_for_different_owners_uses_opaque_distinct_object_partitions() -> None:
    reservations = service()

    first = reservations.reserve("owner-alpha@example.test", request())
    second = reservations.reserve("owner-beta@example.test", request())

    assert first.object_key != second.object_key
    assert f"/{MEDIA_ID}/" in str(first.object_key)
    assert f"/{DISCARDED_DUPLICATE_ID}/" in str(second.object_key)
    assert "owner-alpha" not in str(first.object_key)
    assert "owner-beta" not in str(second.object_key)


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"file_name": "bird?.jpg"}, "UPLOAD_FILE_NAME_INVALID"),
        ({"file_name": ".hidden.jpg"}, "UPLOAD_FILE_NAME_INVALID"),
        ({"file_name": "bird.exe"}, "UPLOAD_EXTENSION_UNSUPPORTED"),
        ({"file_name": "bird.mp4"}, "UPLOAD_MEDIA_TYPE_MISMATCH"),
        ({"size_bytes": 1025}, "UPLOAD_TOO_LARGE"),
    ],
)
def test_invalid_upload_metadata_is_rejected(changes: dict[str, object], expected_code: str) -> None:
    with pytest.raises(ApiError) as raised:
        service().reserve("owner-123", request(**changes))

    assert raised.value.status_code == 422
    assert raised.value.code == expected_code


def test_contract_rejects_paths_and_non_lowercase_sha256() -> None:
    with pytest.raises(ValidationError):
        request(file_name="../bird.jpg")
    with pytest.raises(ValidationError):
        request(sha256="A" * 64)


class SlowAtomicBoundaryRepository(InMemoryMediaRepository):
    """Exposes a deterministic race when orchestration does not serialize the fake."""

    def reserve_upload(self, owner_sub: str, sha256: str, media_id: UUID) -> ReservationResult:
        key = (owner_sub, sha256)
        existing = self._reservations.get(key)
        time.sleep(0.05)
        if existing is not None:
            return ReservationResult(created=False, media_id=existing)
        self._reservations[key] = media_id
        return ReservationResult(created=True, media_id=media_id)


def test_concurrent_reservations_create_one_media_record() -> None:
    repository = SlowAtomicBoundaryRepository()
    reservations = service(repository)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: reservations.reserve("owner-123", request()),
                range(2),
            )
        )

    assert sorted(response.duplicate for response in responses) == [False, True]
    assert len({response.media_id for response in responses}) == 1
    assert len(repository._records) == 1
