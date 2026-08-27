from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.common.contracts.models import MediaRecord
from backend.common.providers.interfaces import ReservationResult


@dataclass(frozen=True, slots=True)
class MediaPage:
    records: tuple[MediaRecord, ...]
    continuation_token: str | None


class InMemoryPagedMediaRepository:
    """Deterministic owner-partitioned repository for local use and tests."""

    def __init__(self, *, page_size: int = 50) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._page_size = page_size
        self._reservations: dict[tuple[str, str], UUID] = {}
        self._records: dict[tuple[str, UUID], MediaRecord] = {}

    def reserve_upload(self, owner_sub: str, sha256: str, media_id: UUID) -> ReservationResult:
        key = (owner_sub, sha256)
        existing = self._reservations.get(key)
        if existing is not None:
            return ReservationResult(created=False, media_id=existing)
        self._reservations[key] = media_id
        return ReservationResult(created=True, media_id=media_id)

    def upsert(self, record: MediaRecord) -> None:
        self._records[(record.owner_sub, record.media_id)] = record

    def get(self, owner_sub: str, media_id: UUID) -> MediaRecord | None:
        return self._records.get((owner_sub, media_id))

    def list_for_owner(self, owner_sub: str) -> list[MediaRecord]:
        return self._owned(owner_sub)

    def find_by_original_uri(self, storage_uri: str) -> MediaRecord | None:
        return next(
            (
                record
                for record in self._records.values()
                if str(record.original_storage_uri) == storage_uri
            ),
            None,
        )

    def find_by_storage_uri(self, owner_sub: str, storage_uri: str) -> MediaRecord | None:
        for record in self._owned(owner_sub):
            if storage_uri in {
                str(record.original_storage_uri),
                str(record.thumbnail_storage_uri) if record.thumbnail_storage_uri else None,
            }:
                return record
        return None

    def query_by_tags(
        self,
        owner_sub: str,
        minimum_counts: dict[str, int],
    ) -> list[MediaRecord]:
        normalized_required = {tag.casefold(): count for tag, count in minimum_counts.items()}
        return [
            record
            for record in self._owned(owner_sub)
            if _meets_minimum_counts(record, normalized_required)
        ]

    def query_by_species(self, owner_sub: str, species: str) -> list[MediaRecord]:
        normalized = species.casefold()
        return [
            record
            for record in self._owned(owner_sub)
            if any(tag.casefold() == normalized for tag in record.tag_counts)
            or any(tag.casefold() == normalized for tag in record.manual_tags)
        ]

    def query_tags_page(
        self,
        owner_sub: str,
        minimum_counts: dict[str, int],
        *,
        continuation_token: str | None = None,
    ) -> MediaPage:
        return self._page(
            self.query_by_tags(owner_sub, minimum_counts),
            continuation_token,
        )

    def query_species_page(
        self,
        owner_sub: str,
        species: str,
        *,
        continuation_token: str | None = None,
    ) -> MediaPage:
        return self._page(
            self.query_by_species(owner_sub, species),
            continuation_token,
        )

    def delete(self, owner_sub: str, media_id: UUID) -> bool:
        return self._records.pop((owner_sub, media_id), None) is not None

    def _owned(self, owner_sub: str) -> list[MediaRecord]:
        return sorted(
            (
                record
                for (record_owner, _), record in self._records.items()
                if record_owner == owner_sub
            ),
            key=lambda record: record.media_id,
        )

    def _page(
        self,
        records: list[MediaRecord],
        continuation_token: str | None,
    ) -> MediaPage:
        try:
            offset = 0 if continuation_token is None else int(continuation_token)
        except ValueError as exc:
            raise ValueError("invalid continuation token") from exc
        if offset < 0 or offset > len(records):
            raise ValueError("invalid continuation token")
        values = tuple(records[offset : offset + self._page_size])
        next_offset = offset + len(values)
        next_token = str(next_offset) if next_offset < len(records) else None
        return MediaPage(records=values, continuation_token=next_token)


def _meets_minimum_counts(record: MediaRecord, required: dict[str, int]) -> bool:
    available = {tag.casefold(): count for tag, count in record.tag_counts.items()}
    return all(available.get(tag, 0) >= count for tag, count in required.items())
