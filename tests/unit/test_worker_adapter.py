from __future__ import annotations

import json

import worker_adapter
from backend.common.contracts.models import TaggingCompletedEvent
from datetime import UTC, datetime
from uuid import UUID


class SecretClient:
    def __init__(self, payload: dict[str, str]) -> None:
        self._payload = payload

    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
        assert SecretId == "worker-secret"
        return {"SecretString": json.dumps(self._payload)}


def test_cosmos_key_is_loaded_from_secrets_manager(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_WORKER_SECRET_ARN", "worker-secret")
    monkeypatch.setattr(worker_adapter.boto3, "client", lambda *args, **kwargs: SecretClient({"cosmos_key": "key-value"}))
    worker_adapter._cosmos_credential.cache_clear()

    assert worker_adapter._cosmos_credential() == "key-value"

    worker_adapter._cosmos_credential.cache_clear()


def test_health_check_reaches_repository_without_processing_media(monkeypatch) -> None:
    class Repository:
        def __init__(self) -> None:
            self.owners: list[str] = []

        def list_for_owner(self, owner_sub: str) -> list[object]:
            self.owners.append(owner_sub)
            return []

    repository = Repository()
    monkeypatch.setattr(
        worker_adapter,
        "_build",
        lambda: (object(), object(), object(), object(), repository, object()),
    )

    response = worker_adapter.handler({"health_check": True}, None)

    assert response == {"status": "ok", "database": "cosmos"}
    assert repository.owners == ["__worker_healthcheck__"]


def test_model_check_forces_runtime_loading(monkeypatch) -> None:
    class Inference:
        def __init__(self) -> None:
            self.loaded = False

        def _get_runtime(self) -> None:
            self.loaded = True

    inference = Inference()
    monkeypatch.setattr(
        worker_adapter,
        "_build",
        lambda: (object(), object(), object(), object(), object(), inference),
    )

    response = worker_adapter.handler({"model_check": True}, None)

    assert response == {"status": "ok", "model": "loaded"}
    assert inference.loaded is True


def test_worker_event_publisher_routes_completion_to_eventbridge() -> None:
    class Sqs:
        def send_message(self, **kwargs: object) -> None:
            raise AssertionError(f"unexpected SQS call: {kwargs}")

    class Events:
        def __init__(self) -> None:
            self.entries: list[dict[str, object]] = []

        def put_events(self, *, Entries: list[dict[str, object]]) -> dict[str, object]:
            self.entries = Entries
            return {"FailedEntryCount": 0}

    events = Events()
    publisher = worker_adapter.WorkerEventPublisher(Sqs(), "queue", events, "application-events")
    publisher.publish(TaggingCompletedEvent(
        schema_version="1.0",
        event_id=UUID("11111111-1111-4111-8111-111111111111"),
        media_id=UUID("22222222-2222-4222-8222-222222222222"),
        owner_sub="owner",
        tag_counts={"dingo": 1},
        model_version="test",
        occurred_at=datetime(2026, 8, 28, tzinfo=UTC),
    ))

    assert events.entries[0]["EventBusName"] == "application-events"
    assert events.entries[0]["DetailType"] == "TaggingCompleted"
    assert json.loads(str(events.entries[0]["Detail"]))["owner_sub"] == "owner"
