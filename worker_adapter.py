"""AWS SQS/Lambda adapter for S3 media events and prepared-media tagging.

The Lambda receives one SQS message at a time. S3 notifications are processed
by the image/video handlers; a ``MediaPreparedEvent`` in the same queue is
processed by the tagging worker. Batch item failures let SQS retry only the
message that failed.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from uuid import UUID, uuid4

import boto3
from dataclasses import dataclass
from urllib.parse import unquote_plus

from backend.azure_api.media.cosmos_repository import CosmosPagedMediaRepository
from backend.common.contracts.models import MediaPreparedEvent
from backend.common.providers.fakes import FixedClock
from backend.common.providers.interfaces import EventPublisher, IdGenerator, ObjectStorage
from backend.media_processor.images.handler import ImageEventHandler, ObjectHead as ImageHead
from backend.media_processor.images.thumbnail import PillowThumbnailer, ThumbnailConfig
from backend.media_processor.videos.handler import ObjectHead as VideoHead, VideoEventHandler
from backend.media_processor.videos.processing import VideoLimits, VideoProcessor
from backend.media_processor.videos import FfmpegVideoBackend
from backend.tagging.inference.local_runtime import LocalWildlifeInferenceService
from backend.tagging.worker.service import TaggingWorker


class S3Storage(ObjectStorage):
    def __init__(self, client, bucket: str) -> None:
        self._client, self._bucket = client, bucket

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        return [item["Key"] for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix) for item in page.get("Contents", [])]

    def delete_keys(self, keys: list[str]) -> None:
        if keys:
            self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": [{"Key": key} for key in keys]})

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return False
            raise
        return True


class S3Inspector:
    def __init__(self, client, bucket: str) -> None:
        self._client, self._bucket = client, bucket

    def inspect(self, key: str):
        head = self._client.head_object(Bucket=self._bucket, Key=key)
        return ObjectHead(
            content_type=str(head.get("ContentType", "application/octet-stream")),
            metadata={str(key).lower(): str(value) for key, value in head.get("Metadata", {}).items()},
            version_id=head.get("VersionId"),
        )


@dataclass(frozen=True, slots=True)
class ObjectHead:
    content_type: str
    metadata: dict[str, str]
    version_id: str | None = None


class SqsPublisher(EventPublisher):
    def __init__(self, client, queue_url: str) -> None:
        self._client, self._queue_url = client, queue_url

    def publish(self, event: object) -> None:
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
        self._client.send_message(QueueUrl=self._queue_url, MessageBody=json.dumps(payload))


class UuidIds(IdGenerator):
    def new_uuid(self) -> UUID:
        return uuid4()


@lru_cache(maxsize=1)
def _cosmos_credential():
    secret_arn = os.environ["AZURE_WORKER_SECRET_ARN"]
    response = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION")).get_secret_value(
        SecretId=secret_arn
    )
    try:
        payload = json.loads(response["SecretString"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Azure worker credential secret is invalid") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Azure worker credential secret is invalid")
    cosmos_key = payload.get("cosmos_key")
    if isinstance(cosmos_key, str) and cosmos_key:
        return cosmos_key
    try:
        tenant_id = payload["tenant_id"]
        client_id = payload["client_id"]
        client_secret = payload["client_secret"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("Azure worker credential secret is invalid") from error
    from azure.identity import ClientSecretCredential

    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )


class ReservationAdapter:
    """Reservation protocol backed by the Cosmos media container."""

    def __init__(self, repository: CosmosPagedMediaRepository) -> None:
        self._repository = repository

    def find_by_original_uri(self, storage_uri: str):
        return self._repository.get_record_for_original(storage_uri)

    def claim_event(self, media_id: UUID, event_token: str) -> bool:
        return self._repository.claim_event(media_id, event_token)

    def release_event(self, media_id: UUID, event_token: str) -> None:
        self._repository.release_event(media_id, event_token)

    def release_claim(self, media_id: UUID, event_token: str) -> None:
        self.release_event(media_id, event_token)

    def mark_prepared(self, media_id: UUID, thumbnail_uri: str, frame_uris: list[str] | None = None) -> None:
        record = self._repository.get_by_id_any_owner(media_id)
        if record is not None:
            self._repository.upsert(record.model_copy(update={"thumbnail_storage_uri": thumbnail_uri, "status": "prepared"}))

    def mark_failed(self, media_id: UUID, code: str, message: str) -> None:
        del code, message
        record = self._repository.get_by_id_any_owner(media_id)
        if record is not None:
            self._repository.upsert(record.model_copy(update={"status": "failed"}))


def _build():
    region = os.environ.get("AWS_REGION", "ap-southeast-2")
    bucket = os.environ["MEDIA_BUCKET"]
    queue_url = os.environ["MEDIA_QUEUE_URL"]
    s3 = boto3.client("s3", region_name=region)
    sqs = boto3.client("sqs", region_name=region)
    storage = S3Storage(s3, bucket)
    publisher = SqsPublisher(sqs, queue_url)
    from azure.cosmos import CosmosClient
    cosmos = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=_cosmos_credential())
    container = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE", "bioarchive")).get_container_client("media")
    repository = CosmosPagedMediaRepository(container)
    reservations = ReservationAdapter(repository)
    inspector = S3Inspector(s3, bucket)
    clock = FixedClock(datetime.now(UTC))
    ids = UuidIds()
    image = ImageEventHandler(bucket_name=bucket, storage=storage, inspector=inspector, reservations=reservations, publisher=publisher, thumbnailer=PillowThumbnailer(ThumbnailConfig()), clock=clock, ids=ids, recompute_checksum=True)
    video = VideoEventHandler(bucket_name=bucket, storage=storage, inspector=inspector, reservations=reservations, publisher=publisher, processor=VideoProcessor(FfmpegVideoBackend(), VideoLimits(max_input_bytes=5_368_709_120, max_duration_seconds=3600, max_frames=3600, timeout_seconds=30, supported_containers=("mp4", "mov"), supported_codecs=("h264", "hevc"))), clock=clock, ids=ids, recompute_checksum=True)
    inference = LocalWildlifeInferenceService(storage=storage, model_dir=os.environ["ML_MODEL_DIR"], device=os.environ.get("ML_DEVICE", "cpu"), detection_threshold=float(os.environ.get("ML_DETECTION_THRESHOLD", "0.05")), classification_threshold=float(os.environ.get("ML_CLASSIFICATION_THRESHOLD", "0.5")))
    tagging = TaggingWorker(storage=storage, inference=inference, repository=repository, publisher=publisher, clock=clock, ids=ids)
    return s3, image, video, tagging, repository, inference


def handler(event, context):
    del context
    s3, image, video, tagging, repository, inference = _build()
    if event.get("health_check") is True:
        repository.list_for_owner("__worker_healthcheck__")
        return {"status": "ok", "database": "cosmos"}
    if event.get("model_check") is True:
        inference._get_runtime()  # type: ignore[attr-defined]
        return {"status": "ok", "model": "loaded"}
    temporary = event.get("temporary_query")
    if isinstance(temporary, dict):
        bucket = str(temporary.get("bucket", ""))
        key = str(temporary.get("key", ""))
        if bucket != os.environ["MEDIA_BUCKET"] or not key.startswith("temporary-query/"):
            raise ValueError("temporary object is outside the configured bucket")
        content_type = s3.head_object(Bucket=bucket, Key=key).get("ContentType", "")
        if content_type.startswith("video/"):
            result = video._processor.process(storage.get_bytes(key))  # type: ignore[attr-defined]
            request_prefix = key.rsplit("/", 1)[0]
            inference_uris = []
            for timestamp, frame in zip(result.timestamps, result.frames, strict=True):
                frame_key = f"{request_prefix}/frames/{timestamp:06d}.jpg"
                storage.put_bytes(frame_key, frame, content_type="image/jpeg")
                inference_uris.append(f"s3://{bucket}/{frame_key}")
        elif content_type in {"image/jpeg", "image/png"}:
            inference_uris = [f"s3://{bucket}/{key}"]
        else:
            raise ValueError("temporary object media type is unsupported")
        inferred = inference.infer(inference_uris)
        return {"status": "ok", "tag_counts": inferred.tag_counts, "model_version": inferred.model_version}
    failures = []
    for message in event.get("Records", []):
        try:
            body = json.loads(message.get("body", "{}"))
            if "schema_version" in body and "media_id" in body and "media_type" in body:
                tagging.process(MediaPreparedEvent.model_validate(body))
            elif body.get("Records"):
                # Inspect the first object to select the media processor.
                record = body["Records"][0]
                key = unquote_plus(record["s3"]["object"]["key"])
                content_type = s3.head_object(Bucket=os.environ["MEDIA_BUCKET"], Key=key)["ContentType"]
                (video if content_type.startswith("video/") else image).handle(body)
        except Exception:
            failures.append({"itemIdentifier": message.get("messageId", "unknown")})
    return {"batchItemFailures": failures}
