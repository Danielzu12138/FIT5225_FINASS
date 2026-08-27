from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID


class CosmosDeliveryLedger:
    """Durable notification deduplication ledger."""

    def __init__(self, container: Any) -> None:
        self._container = container

    @staticmethod
    def _id(event_id: UUID, subscription_id: UUID) -> str:
        return f"{event_id}:{subscription_id}"

    def contains(self, event_id: UUID, subscription_id: UUID) -> bool:
        item_id = self._id(event_id, subscription_id)
        try:
            self._container.read_item(item=item_id, partition_key=item_id)
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return False
            raise
        return True

    def mark_delivered(self, event_id: UUID, subscription_id: UUID) -> None:
        item_id = self._id(event_id, subscription_id)
        try:
            self._container.create_item({"id": item_id, "event_id": str(event_id), "subscription_id": str(subscription_id)})
        except Exception as error:
            if getattr(error, "status_code", None) != 409:
                raise


class CosmosDeletionOperationStore:
    """Persists resumable cross-cloud deletion operations in Cosmos DB."""

    def __init__(self, container: Any) -> None:
        self._container = container

    @staticmethod
    def _id(owner_sub: str, storage_uri: str) -> str:
        return "operation:" + hashlib.sha256(f"{owner_sub}\0{storage_uri}".encode()).hexdigest()

    def get(self, owner_sub: str, storage_uri: str):
        from backend.aws_api.management.deletion import DeletionOperation

        item_id = self._id(owner_sub, storage_uri)
        try:
            item = self._container.read_item(item=item_id, partition_key=owner_sub)
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return None
            raise
        return DeletionOperation(
            operation_id=UUID(str(item["operation_id"])),
            owner_sub=str(item["owner_sub"]),
            storage_uri=str(item["storage_uri"]),
            media_id=UUID(str(item["media_id"])),
            object_keys=[str(key) for key in item.get("object_keys", [])],
            status=str(item.get("status", "marked")),
            error=item.get("error"),
        )

    def put(self, operation) -> None:
        self._container.upsert_item({
            "id": self._id(operation.owner_sub, operation.storage_uri),
            "owner_sub": operation.owner_sub,
            "operation_id": str(operation.operation_id),
            "storage_uri": operation.storage_uri,
            "media_id": str(operation.media_id),
            "object_keys": list(operation.object_keys),
            "status": operation.status,
            "error": operation.error,
        })
