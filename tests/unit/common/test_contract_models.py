from __future__ import annotations

import importlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError


def models_module():
    return importlib.import_module("backend.common.contracts.models")


def test_upload_request_rejects_non_lowercase_sha256() -> None:
    models = models_module()

    with pytest.raises(ValidationError):
        models.UploadReservationRequest(
            file_name="image.jpg",
            media_type="image",
            size_bytes=10,
            sha256="A" * 64,
        )


def test_duplicate_response_requires_null_upload_fields() -> None:
    models = models_module()

    response = models.UploadReservationResponse(
        media_id=UUID("22222222-2222-4222-8222-222222222222"),
        duplicate=True,
        status="reserved",
        upload_url=None,
        object_key=None,
        expires_in_seconds=None,
        upload_headers=None,
    )
    assert response.duplicate is True

    with pytest.raises(ValidationError):
        models.UploadReservationResponse(
            media_id=UUID("22222222-2222-4222-8222-222222222222"),
            duplicate=False,
            status="reserved",
            upload_url=None,
            object_key=None,
            expires_in_seconds=None,
            upload_headers=None,
        )


def test_new_upload_response_requires_canonical_signed_headers() -> None:
    models = models_module()

    response = models.UploadReservationResponse(
        media_id=UUID("22222222-2222-4222-8222-222222222222"),
        duplicate=False,
        status="reserved",
        upload_url="https://uploads.example.test/object",
        object_key="originals/media/hash/camera.jpg",
        expires_in_seconds=900,
        upload_headers={
            "Content-Type": "image/jpeg",
            "x-amz-meta-sha256": "a" * 64,
        },
    )

    assert response.upload_headers["Content-Type"] == "image/jpeg"
    with pytest.raises(ValidationError):
        models.UploadReservationResponse(
            media_id=response.media_id,
            duplicate=False,
            status="reserved",
            upload_url=response.upload_url,
            object_key=response.object_key,
            expires_in_seconds=900,
            upload_headers={"Content-Type": "image/jpeg"},
        )


def test_media_prepared_event_is_strict_and_timezone_aware() -> None:
    models = models_module()

    event = models.MediaPreparedEvent(
        schema_version="1.0",
        event_id=UUID("33333333-3333-4333-8333-333333333333"),
        media_id=UUID("22222222-2222-4222-8222-222222222222"),
        owner_sub="user-123",
        sha256="a" * 64,
        media_type="image",
        original_storage_uri="s3://bucket/original.jpg",
        thumbnail_storage_uri="s3://bucket/thumb.jpg",
        frame_storage_uris=[],
        occurred_at=datetime(2026, 8, 22, 4, 0, tzinfo=UTC),
    )
    assert event.occurred_at.tzinfo is UTC

    with pytest.raises(ValidationError):
        models.MediaPreparedEvent.model_validate({**event.model_dump(), "unexpected": True})


def test_tag_query_requires_positive_counts() -> None:
    models = models_module()

    assert models.TagQuery.model_validate({"wombat": 2}).root == {"wombat": 2}
    with pytest.raises(ValidationError):
        models.TagQuery.model_validate({"wombat": 0})
