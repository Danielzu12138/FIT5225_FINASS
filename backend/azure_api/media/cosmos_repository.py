"""Cosmos DB adapter for the owner-partitioned media repository.

The local in-memory repository remains the test double.  This adapter is only
constructed by the Azure Function/cloud composition root and uses the Cosmos
SQL SDK's partition-key queries so an owner can never read another owner's
records.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.common.contracts.models import MediaRecord
from backend.common.providers.interfaces import ReservationResult

from .repository import MediaPage


class CosmosPagedMediaRepository:
    def __init__(self, container: Any, *, page_size: int = 50) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._container = container
        self._page_size = page_size

    def reserve_upload(self, owner_sub: str, sha256: str, media_id: UUID) -> ReservationResult:
        reservation_id = f"reservation:{sha256}"
        try:
            item = self._container.read_item(item=reservation_id, partition_key=owner_sub)
        except Exception as error:
            if not _is_not_found(error):
                raise
            try:
                self._container.create_item(
                    {
                        "id": reservation_id,
                        "kind": "reservation",
                        "owner_sub": owner_sub,
                        "sha256": sha256,
                        "media_id": str(media_id),
                    }
                )
            except Exception as create_error:
                if getattr(create_error, "status_code", None) != 409:
                    raise
                item = self._container.read_item(item=reservation_id, partition_key=owner_sub)
                return ReservationResult(created=False, media_id=UUID(item["media_id"]))
            return ReservationResult(created=True, media_id=media_id)
        return ReservationResult(created=False, media_id=UUID(item["media_id"]))

    def upsert(self, record: MediaRecord) -> None:
        payload = record.model_dump(mode="json")
        payload.update({"id": str(record.media_id), "kind": "media", "owner_sub": record.owner_sub})
        self._container.upsert_item(payload)

    def get(self, owner_sub: str, media_id: UUID) -> MediaRecord | None:
        try:
            item = self._container.read_item(item=str(media_id), partition_key=owner_sub)
        except Exception as error:
            if _is_not_found(error):
                return None
            raise
        return _record(item)

    def get_by_id_any_owner(self, media_id: UUID) -> MediaRecord | None:
        query = "SELECT * FROM c WHERE c.kind = 'media' AND c.id = @id"
        items = list(self._container.query_items(
            query=query,
            parameters=[{"name": "@id", "value": str(media_id)}],
            enable_cross_partition_query=True,
        ))
        return _record(items[0]) if items else None

    def get_record_for_original(self, storage_uri: str) -> MediaRecord | None:
        return self.find_by_original_uri(storage_uri)

    def claim_event(self, media_id: UUID, event_token: str) -> bool:
        record = self.get_by_id_any_owner(media_id)
        if record is None:
            return False
        claim_id = f"claim:{media_id}:{event_token}"
        try:
            self._container.create_item({
                "id": claim_id,
                "kind": "event_claim",
                "owner_sub": record.owner_sub,
                "media_id": str(media_id),
                "event_token": event_token,
            })
        except Exception as error:
            if getattr(error, "status_code", None) == 409:
                return False
            raise
        return True

    def release_event(self, media_id: UUID, event_token: str) -> None:
        record = self.get_by_id_any_owner(media_id)
        if record is None:
            return
        try:
            self._container.delete_item(item=f"claim:{media_id}:{event_token}", partition_key=record.owner_sub)
        except Exception as error:
            if not _is_not_found(error):
                raise

    def list_for_owner(self, owner_sub: str) -> list[MediaRecord]:
        query = "SELECT * FROM c WHERE c.kind = 'media'"
        return [_record(item) for item in self._container.query_items(query=query, partition_key=owner_sub)]

    def find_by_original_uri(self, storage_uri: str) -> MediaRecord | None:
        query = "SELECT * FROM c WHERE c.kind = 'media' AND c.original_storage_uri = @uri"
        items = list(self._container.query_items(
            query=query,
            parameters=[{"name": "@uri", "value": storage_uri}],
            enable_cross_partition_query=True,
        ))
        return _record(items[0]) if items else None

    def find_by_storage_uri(self, owner_sub: str, storage_uri: str) -> MediaRecord | None:
        query = (
            "SELECT * FROM c WHERE c.kind = 'media' AND "
            "(c.original_storage_uri = @uri OR c.thumbnail_storage_uri = @uri)"
        )
        items = self._container.query_items(
            query=query,
            parameters=[{"name": "@uri", "value": storage_uri}],
            partition_key=owner_sub,
        )
        item = next(iter(items), None)
        return _record(item) if item else None

    def query_by_tags_page(
        self, owner_sub: str, minimum_counts: dict[str, int], *, continuation_token: str | None = None
    ) -> MediaPage:
        records = self._query_owner(owner_sub)
        normalized = {key.casefold(): value for key, value in minimum_counts.items()}
        filtered = [record for record in records if _meets_counts(record, normalized)]
        return self._page(filtered, continuation_token)

    def query_by_species_page(
        self, owner_sub: str, species: str, *, continuation_token: str | None = None
    ) -> MediaPage:
        records = self._query_owner(owner_sub)
        target = species.casefold()
        filtered = [
            record for record in records
            if target in {tag.casefold() for tag in record.tag_counts}
            or target in {tag.casefold() for tag in record.manual_tags}
        ]
        return self._page(filtered, continuation_token)

    def query_by_tags(self, owner_sub: str, minimum_counts: dict[str, int]) -> list[MediaRecord]:
        return self._collect(lambda token: self.query_by_tags_page(owner_sub, minimum_counts, continuation_token=token))

    def query_by_species(self, owner_sub: str, species: str) -> list[MediaRecord]:
        return self._collect(lambda token: self.query_by_species_page(owner_sub, species, continuation_token=token))

    def delete(self, owner_sub: str, media_id: UUID) -> bool:
        try:
            self._container.delete_item(item=str(media_id), partition_key=owner_sub)
        except Exception as error:
            if _is_not_found(error):
                return False
            raise
        return True

    def _query_owner(self, owner_sub: str) -> list[MediaRecord]:
        query = "SELECT * FROM c WHERE c.kind = 'media'"
        return [_record(item) for item in self._container.query_items(query=query, partition_key=owner_sub)]

    def _page(self, records: list[MediaRecord], token: str | None) -> MediaPage:
        try:
            offset = 0 if token is None else int(token)
        except ValueError as error:
            raise ValueError("invalid continuation token") from error
        values = tuple(sorted(records, key=lambda item: item.media_id)[offset : offset + self._page_size])
        next_offset = offset + len(values)
        return MediaPage(records=values, continuation_token=str(next_offset) if next_offset < len(records) else None)

    @staticmethod
    def _collect(fetch):
        token = None
        result = []
        while True:
            page = fetch(token)
            result.extend(page.records)
            if page.continuation_token is None:
                return sorted(result, key=lambda item: item.media_id)
            token = page.continuation_token


def _record(item: dict[str, Any]) -> MediaRecord:
    return MediaRecord.model_validate({key: value for key, value in item.items() if key not in {"id", "kind", "_rid", "_self", "_etag", "_attachments", "_ts"}})


def _meets_counts(record: MediaRecord, required: dict[str, int]) -> bool:
    available = {tag.casefold(): count for tag, count in record.tag_counts.items()}
    # Manual tags are presence-only, so they contribute one match.
    for tag in record.manual_tags:
        available.setdefault(tag.casefold(), 1)
    return all(available.get(tag, 0) >= count for tag, count in required.items())


def _is_not_found(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 404
