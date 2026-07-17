"""Exercise media dataset: sync and lookup for hasaneyldrm/exercises-dataset.

The dataset (1,324 exercises, one animation GIF + step-by-step instructions in
10 languages each) is cloned once into a local cache and refreshed with a
fast-forward pull at every server start (background thread, offline-tolerant:
a failed pull leaves the existing clone usable). The index resolves a program
block to a dataset record through the curated seed mapping first
(data/dataset_map.yaml), then an exact normalised-name match, then a
high-cutoff fuzzy match — media enrichment is best-effort by design, so an
unresolved exercise renders without media rather than with the wrong GIF.
"""

import base64
import difflib
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml

DATASET_REPO_URL = "https://github.com/hasaneyldrm/exercises-dataset"
ENV_VAR = "PERFORMANCE_AGENT_EXERCISES_DATASET"
NO_SYNC_ENV_VAR = "PERFORMANCE_AGENT_NO_DATASET_SYNC"

# First clone downloads ~125 MB of GIFs; later pulls are near-instant.
_SYNC_TIMEOUT_S = 900
_FUZZY_CUTOFF = 0.9
_MAP_PACKAGE = "performance_agent.exercises"


def resolve_dataset_dir() -> Path:
    """Return the dataset cache directory (never creates it).

    PERFORMANCE_AGENT_EXERCISES_DATASET overrides the default shared cache in
    ~/.performance-agent/cache/exercises-dataset.
    """
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".performance-agent" / "cache" / "exercises-dataset"


@dataclass(frozen=True)
class SyncResult:
    """Outcome of one dataset sync attempt."""

    path: Path
    action: Literal["cloned", "updated", "failed"]
    detail: str = ""


def sync_dataset(target: Path | None = None, timeout_s: float = _SYNC_TIMEOUT_S) -> SyncResult:
    """Clone the dataset on first run, fast-forward pull afterwards.

    Never raises on network or git failure — a `failed` result with the git
    message is returned instead, and any existing clone stays usable offline.
    """
    directory = target or resolve_dataset_dir()
    if (directory / ".git").is_dir():
        command = ["git", "-C", str(directory), "pull", "--ff-only", "--quiet"]
        action: Literal["cloned", "updated"] = "updated"
    else:
        directory.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--depth", "1", "--quiet", DATASET_REPO_URL, str(directory)]
        action = "cloned"
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return SyncResult(directory, "failed", str(exc))
    if completed.returncode != 0:
        return SyncResult(directory, "failed", completed.stderr.strip())
    return SyncResult(directory, action)


def start_background_sync() -> threading.Thread | None:
    """Kick off a daemon-thread sync so server startup never blocks on the network.

    Returns None without syncing when PERFORMANCE_AGENT_NO_DATASET_SYNC is set
    (tests and CI must not download ~125 MB of media as a side effect).
    """
    if os.environ.get(NO_SYNC_ENV_VAR):
        return None
    thread = threading.Thread(target=sync_dataset, name="exercises-dataset-sync", daemon=True)
    thread.start()
    return thread


@dataclass(frozen=True)
class DatasetExercise:
    """One dataset record: media paths plus localised instructions."""

    dataset_id: str
    name: str
    equipment: str
    target: str
    secondary_muscles: tuple[str, ...]
    gif_path: Path
    instruction_steps: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def steps(self, locale: str) -> tuple[str, ...]:
        """Return instruction steps in the locale, falling back to English."""
        return self.instruction_steps.get(locale) or self.instruction_steps.get("en", ())

    def gif_data_uri(self) -> str | None:
        """Return the animation GIF as a base64 data URI, or None if missing."""
        try:
            payload = self.gif_path.read_bytes()
        except OSError:
            return None
        return "data:image/gif;base64," + base64.b64encode(payload).decode("ascii")


def _normalise(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def load_seed_dataset_map() -> dict[str, str]:
    """Return the packaged curated mapping: seed exercise id -> dataset record id."""
    text = (resources.files(_MAP_PACKAGE) / "data" / "dataset_map.yaml").read_text("utf-8")
    loaded = yaml.safe_load(text)
    return {str(seed): str(dataset_id) for seed, dataset_id in loaded.items()}


class ExerciseMediaIndex:
    """Read-only lookup over a synced dataset clone."""

    def __init__(self, exercises: list[DatasetExercise], seed_map: dict[str, str]) -> None:
        """Index the records by id and normalised name (see `load`)."""
        self._by_id = {exercise.dataset_id: exercise for exercise in exercises}
        self._by_norm_name = {_normalise(exercise.name): exercise for exercise in exercises}
        self._seed_map = seed_map

    @classmethod
    def load(cls, directory: Path | None = None) -> "ExerciseMediaIndex":
        """Load data/exercises.json from the dataset clone.

        Raises FileNotFoundError when the clone (or its data file) is absent —
        callers treat that as "no media available yet" and degrade gracefully.
        """
        base = directory or resolve_dataset_dir()
        records = json.loads((base / "data" / "exercises.json").read_text("utf-8"))
        exercises = [
            DatasetExercise(
                dataset_id=str(record["id"]),
                name=str(record["name"]),
                equipment=str(record.get("equipment", "")),
                target=str(record.get("target", "")),
                secondary_muscles=tuple(record.get("secondary_muscles", ())),
                gif_path=base / str(record["gif_url"]),
                instruction_steps={
                    lang: tuple(steps)
                    for lang, steps in record.get("instruction_steps", {}).items()
                },
            )
            for record in records
        ]
        return cls(exercises, load_seed_dataset_map())

    def resolve(self, name: str, exercise_id: str | None = None) -> DatasetExercise | None:
        """Resolve a program block to a dataset record, or None when unsure.

        Order: curated seed mapping (by exercise_id), exact normalised name,
        then fuzzy name match above a high cutoff — never a wild guess.
        """
        if exercise_id is not None:
            mapped = self._seed_map.get(exercise_id)
            if mapped is not None and mapped in self._by_id:
                return self._by_id[mapped]
        normalised = _normalise(name)
        exact = self._by_norm_name.get(normalised)
        if exact is not None:
            return exact
        close = difflib.get_close_matches(
            normalised, self._by_norm_name.keys(), n=1, cutoff=_FUZZY_CUTOFF
        )
        return self._by_norm_name[close[0]] if close else None
