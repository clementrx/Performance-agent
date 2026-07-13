"""Packaging regression: the wheel must ship everything the runtime needs."""

import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def wheel_path(tmp_path_factory) -> Path:
    out_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=120,
    )
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def test_wheel_ships_the_seed_corpus(wheel_path):
    assert "performance_agent/evidence/data/seed_corpus.yaml" in _names(wheel_path)


def test_wheel_ships_the_seed_performance_models(wheel_path):
    names = _names(wheel_path)
    for slug in ("sprint-100m", "running-10k", "powerlifting", "football"):
        assert f"performance_agent/models/data/seed/{slug}.yaml" in names


def test_wheel_ships_the_seed_exercise_library(wheel_path):
    assert "performance_agent/exercises/data/seed_exercises.yaml" in _names(wheel_path)


def test_wheel_ships_the_license(wheel_path):
    names = _names(wheel_path)
    assert any(name.endswith("licenses/LICENSE") or name.endswith("LICENSE") for name in names)


def test_wheel_declares_the_console_script(wheel_path):
    with zipfile.ZipFile(wheel_path) as archive:
        entry_points = next(n for n in archive.namelist() if n.endswith("entry_points.txt"))
        content = archive.read(entry_points).decode("utf-8")
    assert "performance-agent = performance_agent.server.app:main" in content


def test_wheel_has_no_test_or_skill_leakage(wheel_path):
    names = _names(wheel_path)
    assert not any(name.startswith(("tests/", "skills/")) for name in names)


def test_metadata_carries_classifiers(wheel_path):
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(n for n in archive.namelist() if n.endswith("METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    assert "Classifier: Development Status :: 3 - Alpha" in metadata
    assert "Classifier: Programming Language :: Python :: 3.13" in metadata
    assert "Keywords:" in metadata
