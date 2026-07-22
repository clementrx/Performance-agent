import base64
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from performance_agent.exercises import dataset
from performance_agent.exercises.dataset import ExerciseMediaIndex, sync_dataset
from performance_agent.memory.exercise_library import load_seed_exercises

GIF_BYTES = b"GIF89a-not-really-a-gif"


def write_fixture_dataset(base: Path) -> Path:
    (base / "data").mkdir(parents=True)
    (base / "videos").mkdir()
    records = [
        {
            "id": "0043",
            "name": "barbell full squat",
            "equipment": "barbell",
            "target": "glutes",
            "secondary_muscles": ["quads", "calves"],
            "gif_url": "videos/0043.gif",
            "instruction_steps": {
                "en": ["Stand with the bar on your back.", "Squat down and up."],
                "fr": ["Barre sur le dos.", "Descendez puis remontez."],
            },
        },
        {
            "id": "0025",
            "name": "barbell bench press",
            "equipment": "barbell",
            "target": "pectorals",
            "secondary_muscles": [],
            "gif_url": "videos/0025.gif",
            "instruction_steps": {"en": ["Press the bar."]},
        },
    ]
    (base / "data" / "exercises.json").write_text(json.dumps(records))
    (base / "videos" / "0043.gif").write_bytes(GIF_BYTES)
    # 0025.gif intentionally missing to exercise the no-media path.
    return base


@pytest.fixture
def index(tmp_path):
    return ExerciseMediaIndex.load(write_fixture_dataset(tmp_path / "ds"))


def test_load_missing_clone_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ExerciseMediaIndex.load(tmp_path / "nowhere")


def test_resolve_by_curated_seed_id(index):
    resolved = index.resolve("Back Squat", exercise_id="back-squat")
    assert resolved is not None
    assert resolved.dataset_id == "0043"


def test_resolve_by_exact_name_ignores_case_and_punctuation(index):
    resolved = index.resolve("Barbell Bench-Press!")
    assert resolved is not None
    assert resolved.dataset_id == "0025"


def test_resolve_fuzzy_close_name(index):
    resolved = index.resolve("barbell full squats")
    assert resolved is not None
    assert resolved.dataset_id == "0043"


def test_resolve_unknown_returns_none(index):
    assert index.resolve("Hill Sprint", exercise_id="hill-sprint") is None
    assert index.resolve("nordic curl") is None


def test_steps_locale_with_english_fallback(index):
    squat = index.resolve("barbell full squat")
    assert squat.steps("fr") == ("Barre sur le dos.", "Descendez puis remontez.")
    bench = index.resolve("barbell bench press")
    assert bench.steps("fr") == ("Press the bar.",)


def test_gif_data_uri_roundtrip_and_missing_file(index):
    squat = index.resolve("barbell full squat")
    uri = squat.gif_data_uri()
    assert uri.startswith("data:image/gif;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == GIF_BYTES
    bench = index.resolve("barbell bench press")
    assert bench.gif_data_uri() is None


def test_curated_map_only_references_seed_ids():
    seed_ids = set(load_seed_exercises())
    unknown = set(dataset.load_seed_dataset_map()) - seed_ids
    assert not unknown, f"dataset_map.yaml references unknown seed ids: {sorted(unknown)}"


def test_curated_map_ids_are_dataset_shaped():
    for dataset_id in dataset.load_seed_dataset_map().values():
        assert dataset_id.isdigit() and len(dataset_id) == 4


def make_origin(path: Path) -> Path:
    write_fixture_dataset(path)
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(path), *args], check=True, capture_output=True
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", "-A")
    run("commit", "-q", "-m", "seed")
    return path


def test_sync_clones_then_pulls(tmp_path, monkeypatch):
    origin = make_origin(tmp_path / "origin")
    monkeypatch.setattr(dataset, "DATASET_REPO_URL", str(origin))
    clone = tmp_path / "clone"

    first = sync_dataset(clone)
    assert first.action == "cloned", first.detail
    assert (clone / "data" / "exercises.json").is_file()

    (origin / "data" / "extra.txt").write_text("update")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(origin), "commit", "-q", "-m", "update"],
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": "/usr/bin:/bin",
        },
    )

    second = sync_dataset(clone)
    assert second.action == "updated", second.detail
    assert (clone / "data" / "extra.txt").is_file()


def test_sync_failure_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset, "DATASET_REPO_URL", str(tmp_path / "no-such-origin"))
    result = sync_dataset(tmp_path / "clone")
    assert result.action == "failed"
    assert result.detail


def test_background_sync_disabled_by_env(monkeypatch):
    monkeypatch.setenv(dataset.NO_SYNC_ENV_VAR, "1")
    assert dataset.start_background_sync() is None


def test_curated_map_is_valid_yaml_dict():
    mapping = dataset.load_seed_dataset_map()
    assert isinstance(mapping, dict) and len(mapping) > 50
    text = yaml.safe_dump(mapping)
    assert "back-squat" in text


def test_get_by_dataset_id(index):
    assert index.get("0043").name == "barbell full squat"
    assert index.get("9999") is None
