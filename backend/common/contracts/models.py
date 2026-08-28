from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    RootModel,
    StringConstraints,
    field_validator,
    model_validator,
)


Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
StorageUri = Annotated[str, StringConstraints(pattern=r"^s3://[^/]+/.+")]
SpeciesName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorDetail(StrictModel):
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
    message: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    request_id: UUID


class ErrorResponse(StrictModel):
    error: ErrorDetail


class UploadReservationRequest(StrictModel):
    file_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"^[^/\\]+$"),
    ]
    media_type: Literal["image", "video"]
    size_bytes: Annotated[int, Field(ge=1, le=5_368_709_120)]
    sha256: Sha256


class UploadReservationResponse(StrictModel):
    media_id: UUID
    duplicate: bool
    status: Literal["reserved", "uploaded", "processing", "prepared", "ready", "failed"]
    upload_url: HttpUrl | None
    object_key: str | None
    expires_in_seconds: Annotated[int, Field(ge=1, le=3600)] | None
    upload_headers: dict[str, str] | None

    @model_validator(mode="after")
    def enforce_duplicate_shape(self) -> "UploadReservationResponse":
        upload_values = (
            self.upload_url,
            self.object_key,
            self.expires_in_seconds,
            self.upload_headers,
        )
        if self.duplicate and any(value is not None for value in upload_values):
            raise ValueError("duplicate reservations cannot include upload fields")
        if not self.duplicate and any(value is None for value in upload_values):
            raise ValueError("new reservations require all upload fields")
        if not self.duplicate and self.upload_headers is not None:
            if set(self.upload_headers) != {"Content-Type", "x-amz-meta-sha256"}:
                raise ValueError("upload headers must contain the signed content type and sha256 metadata")
            if not self.upload_headers["Content-Type"]:
                raise ValueError("signed upload content type cannot be empty")
            if not re.fullmatch(r"[a-f0-9]{64}", self.upload_headers["x-amz-meta-sha256"]):
                raise ValueError("signed upload sha256 metadata is invalid")
        return self


class MediaPreparedEvent(StrictModel):
    schema_version: Literal["1.0"]
    event_id: UUID
    media_id: UUID
    owner_sub: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    sha256: Sha256
    media_type: Literal["image", "video"]
    original_storage_uri: StorageUri
    thumbnail_storage_uri: StorageUri | None
    frame_storage_uris: list[StorageUri]
    occurred_at: datetime

    @field_validator("frame_storage_uris")
    @classmethod
    def require_unique_frames(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("frame storage URIs must be unique")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class MediaRecord(StrictModel):
    media_id: UUID
    owner_sub: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    sha256: Sha256
    file_name: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    media_type: Literal["image", "video"]
    original_storage_uri: StorageUri
    thumbnail_storage_uri: StorageUri | None
    tag_counts: dict[SpeciesName, Annotated[int, Field(ge=1)]]
    manual_tags: list[SpeciesName]
    model_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    status: Literal["reserved", "uploaded", "processing", "prepared", "ready", "deleting", "failed"]
    created_at: datetime
    updated_at: datetime

    @field_validator("manual_tags")
    @classmethod
    def require_unique_manual_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("manual tags must be unique")
        return value


class TaggingCompletedEvent(StrictModel):
    schema_version: Literal["1.0"]
    event_id: UUID
    media_id: UUID
    owner_sub: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    tag_counts: dict[SpeciesName, Annotated[int, Field(ge=1)]]
    model_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    occurred_at: datetime


class TagQuery(RootModel[dict[str, int]]):
    @field_validator("root")
    @classmethod
    def validate_query(cls, value: dict[str, int]) -> dict[str, int]:
        if not 1 <= len(value) <= 20:
            raise ValueError("tag query requires between 1 and 20 tags")
        tag_pattern = re.compile(r"^[A-Za-z][A-Za-z0-9_. -]{0,127}$")
        if any(not tag_pattern.fullmatch(tag) for tag in value):
            raise ValueError("invalid tag name")
        if any(isinstance(count, bool) or not 1 <= count <= 100_000 for count in value.values()):
            raise ValueError("tag counts must be positive integers")
        return value


class SpeciesQuery(StrictModel):
    species: SpeciesName


class ThumbnailQuery(StrictModel):
    thumbnail_url: HttpUrl


class QueryResult(StrictModel):
    media_id: UUID
    media_type: Literal["image", "video"]
    status: Literal["reserved", "uploaded", "processing", "prepared", "ready", "deleting", "failed"]
    original_url: HttpUrl | None
    thumbnail_url: HttpUrl | None
    tag_counts: dict[SpeciesName, Annotated[int, Field(ge=1)]]
    manual_tags: list[SpeciesName] = Field(default_factory=list)


class QueryResponse(StrictModel):
    results: list[QueryResult]


class BulkTagOperation(StrictModel):
    urls: Annotated[list[HttpUrl], Field(min_length=1, max_length=100)]
    tags: Annotated[list[SpeciesName], Field(min_length=1, max_length=50)]
    operation: Literal[0, 1]


class DeleteRequest(StrictModel):
    urls: Annotated[list[HttpUrl], Field(min_length=1, max_length=100)]


class NotificationSubscription(StrictModel):
    email: Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)]
    tags: Annotated[list[SpeciesName], Field(min_length=1, max_length=50)]
