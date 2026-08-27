from __future__ import annotations

import json

import worker_adapter


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
