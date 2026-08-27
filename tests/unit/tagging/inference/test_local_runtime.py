import os
from pathlib import Path

from backend.common.providers.fakes import InMemoryObjectStorage
from backend.common.providers.interfaces import InferenceResult
from backend.tagging.inference.local_runtime import (
    LocalWildlifeInferenceService,
    _load_labels,
    _temporary_environment,
)


class RecordingRuntime:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, bytes]]] = []

    def infer(self, inputs: list[tuple[str, bytes]]) -> InferenceResult:
        self.calls.append(inputs)
        return InferenceResult(tag_counts={"Bos_taurus": 2}, model_version="test-model")


def test_service_reads_storage_and_reuses_one_runtime(tmp_path: Path) -> None:
    storage = InMemoryObjectStorage()
    storage.put_bytes("temporary-query/one.jpg", b"image", content_type="image/jpeg")
    runtime = RecordingRuntime()
    service = LocalWildlifeInferenceService(
        storage=storage,
        model_dir=tmp_path,
        runtime_factory=lambda: runtime,
    )

    first = service.infer(["s3://media/temporary-query/one.jpg"])
    second = service.infer(["s3://media/temporary-query/one.jpg"])

    assert first == second == InferenceResult(tag_counts={"Bos_taurus": 2}, model_version="test-model")
    assert runtime.calls == [
        [("s3://media/temporary-query/one.jpg", b"image")],
        [("s3://media/temporary-query/one.jpg", b"image")],
    ]


def test_taxonomy_file_maps_to_classifier_species_names(tmp_path: Path) -> None:
    labels = tmp_path / "labels.txt"
    labels.write_text(
        "id;mammalia;order;family;bos;taurus;cattle\n"
        "id;aves;order;family;casuarius;casuarius;southern cassowary\n",
        encoding="utf-8",
    )

    assert _load_labels(labels) == ("Bos_taurus", "Casuarius_casuarius")


def test_temporary_environment_restores_existing_values(monkeypatch) -> None:
    monkeypatch.setenv("PBA_EXISTING", "before")
    monkeypatch.delenv("PBA_NEW", raising=False)

    with _temporary_environment(PBA_EXISTING="during", PBA_NEW="created"):
        assert os.environ["PBA_EXISTING"] == "during"
        assert os.environ["PBA_NEW"] == "created"

    assert os.environ["PBA_EXISTING"] == "before"
    assert "PBA_NEW" not in os.environ
