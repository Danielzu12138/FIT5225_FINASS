from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from backend.aws_api.management import deletion
from backend.azure_api.management import service as management
from backend.common.contracts.models import MediaRecord
from backend.common.providers.fakes import (
    FixedClock,
    InMemoryMediaRepository,
    InMemoryObjectStorage,
    SequenceIdGenerator,
)


MEDIA_ID = UUID("22222222-2222-4222-8222-222222222222")
OPERATION_ID = UUID("44444444-4444-4444-8444-444444444444")
SHA = "a" * 64
NOW = datetime(2026, 8, 22, 11, 0, tzinfo=UTC)
URL = f"https://downloads.example.test/originals/{SHA}/camera.jpg"


def make_record(*, owner_sub: str = "owner") -> MediaRecord:
    created = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    return MediaRecord(
        media_id=MEDIA_ID,
        owner_sub=owner_sub,
        sha256=SHA,
        file_name="camera.jpg",
        media_type="video",
        original_storage_uri=f"s3://media/originals/{SHA}/camera.jpg",
        thumbnail_storage_uri=f"s3://media/derived/{SHA}/thumbnail.jpg",
        tag_counts={"dingo": 2},
        manual_tags=[],
        model_version="speciesnet-1.0.0",
        status="ready",
        created_at=created,
        updated_at=created,
    )


def populate(storage: InMemoryObjectStorage) -> list[str]:
    keys = [
        f"originals/{SHA}/camera.jpg",
        f"derived/{SHA}/thumbnail.jpg",
        f"derived/{SHA}/frames/000001.jpg",
        f"derived/{SHA}/frames/000002.jpg",
    ]
    for key in keys:
        storage.put_bytes(key, b"media", content_type="image/jpeg")
    return keys


def make_service(repository, storage):
    service_type = getattr(deletion, "CrossCloudDeleteService", None)
    store_type = getattr(deletion, "InMemoryDeletionOperationStore", None)
    normalizer_type = getattr(management, "SignedUrlNormalizer", None)
    assert service_type is not None, "CrossCloudDeleteService has not been implemented"
    assert store_type is not None, "InMemoryDeletionOperationStore has not been implemented"
    return service_type(
        repository=repository,
        storage=storage,
        operations=store_type(),
        clock=FixedClock(NOW),
        ids=SequenceIdGenerator([OPERATION_ID]),
        normalizer=normalizer_type(
            download_base_url="https://downloads.example.test",
            bucket_name="media",
        ),
    )


def test_delete_removes_original_thumbnail_all_frames_and_record() -> None:
    repository = InMemoryMediaRepository()
    repository.upsert(make_record())
    storage = InMemoryObjectStorage()
    keys = populate(storage)
    service = make_service(repository, storage)

    outcome = service.delete(owner_sub="owner", urls=[URL])[0]

    assert outcome.status == "deleted"
    assert outcome.operation_id == OPERATION_ID
    assert repository.get("owner", MEDIA_ID) is None
    assert all(storage.exists(key) is False for key in keys)


def test_delete_is_owner_scoped_and_does_not_touch_foreign_objects() -> None:
    repository = InMemoryMediaRepository()
    repository.upsert(make_record(owner_sub="other-owner"))
    storage = InMemoryObjectStorage()
    keys = populate(storage)
    service = make_service(repository, storage)

    outcome = service.delete(owner_sub="owner", urls=[URL])[0]

    assert outcome.status == "not_found"
    assert all(storage.exists(key) for key in keys)
    assert repository.get("other-owner", MEDIA_ID) is not None


def test_same_content_delete_removes_only_the_owners_partitioned_objects() -> None:
    owner_a_id = MEDIA_ID
    owner_b_id = UUID("33333333-3333-4333-8333-333333333333")
    repository = InMemoryMediaRepository()
    storage = InMemoryObjectStorage()

    def partitioned_record(owner_sub: str, media_id: UUID) -> MediaRecord:
        return make_record(owner_sub=owner_sub).model_copy(
            update={
                "media_id": media_id,
                "original_storage_uri": f"s3://media/originals/{media_id}/{SHA}/camera.jpg",
                "thumbnail_storage_uri": f"s3://media/derived/{media_id}/{SHA}/thumbnail.jpg",
            }
        )

    records = [partitioned_record("owner-a", owner_a_id), partitioned_record("owner-b", owner_b_id)]
    for record in records:
        repository.upsert(record)
        prefix = f"{record.media_id}/{record.sha256}"
        storage.put_bytes(f"originals/{prefix}/camera.jpg", b"media", content_type="image/jpeg")
        storage.put_bytes(f"derived/{prefix}/thumbnail.jpg", b"thumb", content_type="image/jpeg")
        storage.put_bytes(f"derived/{prefix}/frames/000001.jpg", b"frame", content_type="image/jpeg")

    service = make_service(repository, storage)
    url = f"https://downloads.example.test/originals/{owner_a_id}/{SHA}/camera.jpg"
    outcome = service.delete(owner_sub="owner-a", urls=[url])[0]

    assert outcome.status == "deleted"
    assert storage.list_keys(f"originals/{owner_a_id}/") == []
    assert storage.list_keys(f"derived/{owner_a_id}/") == []
    assert storage.list_keys(f"originals/{owner_b_id}/") != []
    assert storage.list_keys(f"derived/{owner_b_id}/") != []
    assert repository.get("owner-b", owner_b_id) is not None


def test_database_failure_keeps_recoverable_operation_and_retry_finishes() -> None:
    class FailOnceRepository(InMemoryMediaRepository):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        def delete(self, owner_sub: str, media_id: UUID) -> bool:
            if self.fail:
                self.fail = False
                return False
            return super().delete(owner_sub, media_id)

    repository = FailOnceRepository()
    repository.upsert(make_record())
    storage = InMemoryObjectStorage()
    keys = populate(storage)
    service = make_service(repository, storage)

    first = service.delete(owner_sub="owner", urls=[URL])[0]
    second = service.delete(owner_sub="owner", urls=[URL])[0]

    assert first.status == "failed"
    assert first.operation_id == OPERATION_ID
    assert second.status == "deleted"
    assert second.operation_id == OPERATION_ID
    assert all(storage.exists(key) is False for key in keys)
    assert repository.get("owner", MEDIA_ID) is None


def test_storage_failure_leaves_deleting_record_and_retry_is_safe() -> None:
    class FailOnceStorage(InMemoryObjectStorage):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        def delete_keys(self, keys: list[str]) -> None:
            if self.fail:
                self.fail = False
                raise OSError("temporary storage failure")
            super().delete_keys(keys)

    repository = InMemoryMediaRepository()
    repository.upsert(make_record())
    storage = FailOnceStorage()
    populate(storage)
    service = make_service(repository, storage)

    first = service.delete(owner_sub="owner", urls=[URL])[0]
    marked = repository.get("owner", MEDIA_ID)
    second = service.delete(owner_sub="owner", urls=[URL])[0]

    assert first.status == "failed"
    assert marked is not None and marked.status == "deleting"
    assert second.status == "deleted"
