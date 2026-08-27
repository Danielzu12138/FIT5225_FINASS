from __future__ import annotations

import re
from pathlib import PurePath
from threading import Lock

from backend.common.contracts.models import (
    MediaRecord,
    UploadReservationRequest,
    UploadReservationResponse,
)
from backend.common.errors.models import ApiError
from backend.common.providers.interfaces import (
    Clock,
    IdGenerator,
    MediaRepository,
    ObjectUrlSigner,
)


CONTENT_TYPES: dict[str, tuple[str, str]] = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
}
SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")


def safe_file_name(file_name: str) -> str:
    if not SAFE_FILE_NAME.fullmatch(file_name) or file_name.startswith("."):
        raise ApiError(
            "UPLOAD_FILE_NAME_INVALID",
            "File name must contain only safe letters, numbers, spaces, dots, dashes, or underscores",
            422,
        )
    normalized = re.sub(r"\s+", "-", file_name.strip().lower())
    if normalized in {".", ".."} or PurePath(normalized).name != normalized:
        raise ApiError("UPLOAD_FILE_NAME_INVALID", "File name must not contain a path", 422)
    return normalized


def content_type_for(file_name: str, media_type: str) -> str:
    extension = PurePath(file_name).suffix.lower()
    supported = CONTENT_TYPES.get(extension)
    if supported is None:
        raise ApiError("UPLOAD_EXTENSION_UNSUPPORTED", "File extension is not supported", 422)
    expected_media_type, content_type = supported
    if media_type != expected_media_type:
        raise ApiError(
            "UPLOAD_MEDIA_TYPE_MISMATCH",
            "File extension does not match the declared media type",
            422,
        )
    return content_type


class UploadReservationService:
    def __init__(
        self,
        *,
        repository: MediaRepository,
        url_signer: ObjectUrlSigner,
        clock: Clock,
        ids: IdGenerator,
        bucket_name: str,
        max_size_bytes: int,
        upload_url_ttl_seconds: int = 900,
    ) -> None:
        if not bucket_name or "/" in bucket_name:
            raise ValueError("bucket_name must be an S3 bucket name")
        if max_size_bytes < 1:
            raise ValueError("max_size_bytes must be positive")
        self._repository = repository
        self._url_signer = url_signer
        self._clock = clock
        self._ids = ids
        self._bucket_name = bucket_name
        self._max_size_bytes = max_size_bytes
        self._upload_url_ttl_seconds = upload_url_ttl_seconds
        self._reservation_lock = Lock()

    def reserve(
        self,
        owner_sub: str,
        request: UploadReservationRequest,
    ) -> UploadReservationResponse:
        if not owner_sub.strip():
            raise ApiError("AUTH_SUBJECT_INVALID", "Authenticated owner is required", 401)
        if request.size_bytes > self._max_size_bytes:
            raise ApiError("UPLOAD_TOO_LARGE", "File exceeds the configured upload limit", 422)

        file_name = safe_file_name(request.file_name)
        content_type = content_type_for(file_name, request.media_type)
        with self._reservation_lock:
            candidate_id = self._ids.new_uuid()
            reservation = self._repository.reserve_upload(owner_sub, request.sha256, candidate_id)
            if not reservation.created:
                existing = self._repository.get(owner_sub, reservation.media_id)
                return UploadReservationResponse(
                    media_id=reservation.media_id,
                    duplicate=True,
                    status=existing.status if existing else "reserved",
                    upload_url=None,
                    object_key=None,
                    expires_in_seconds=None,
                    upload_headers=None,
                )

            object_key = f"originals/{reservation.media_id}/{request.sha256}/{file_name}"
            now = self._clock.now_utc()
            self._repository.upsert(
                MediaRecord(
                    media_id=reservation.media_id,
                    owner_sub=owner_sub,
                    sha256=request.sha256,
                    file_name=file_name,
                    media_type=request.media_type,
                    original_storage_uri=f"s3://{self._bucket_name}/{object_key}",
                    thumbnail_storage_uri=None,
                    tag_counts={},
                    manual_tags=[],
                    model_version="pending",
                    status="reserved",
                    created_at=now,
                    updated_at=now,
                )
            )
            upload_url = self._url_signer.create_upload_url(
                object_key,
                content_type=content_type,
                checksum_sha256=request.sha256,
                expires_in_seconds=self._upload_url_ttl_seconds,
            )
            return UploadReservationResponse(
                media_id=reservation.media_id,
                duplicate=False,
                status="reserved",
                upload_url=upload_url,
                object_key=object_key,
                expires_in_seconds=self._upload_url_ttl_seconds,
                upload_headers={
                    "Content-Type": content_type,
                    "x-amz-meta-sha256": request.sha256,
                },
            )
