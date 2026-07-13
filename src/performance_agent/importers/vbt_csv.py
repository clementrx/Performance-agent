"""Parse a velocity-based-training CSV export into structured VbtSet rows.

Common VBT apps (e.g. bar-sensor exports) produce one row per set with the
exercise, load, mean concentric velocity and reps. This importer column-maps the
usual header variants, PARSES and returns VbtSet objects for the caller to
propose — it never writes. A file with no usable rows raises ActivityImportError.
"""

from pathlib import Path

from performance_agent.importers.activity import ActivityImportError, _read_csv_rows, _to_float
from performance_agent.memory.schemas import VbtSet

_EXERCISE_COLUMNS = ("exercise", "lift", "movement", "name")
_LOAD_COLUMNS = ("load_kg", "load", "weight", "weight_kg", "mass_kg")
_VELOCITY_COLUMNS = ("mean_velocity", "mean_vel", "velocity", "mpv", "avg_velocity", "mean_mps")
_TOP_VELOCITY_COLUMNS = ("top_velocity", "peak_velocity", "max_velocity", "peak_vel")
_REPS_COLUMNS = ("reps", "rep", "repetitions", "count")


def _pick(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in columns), None)


def looks_like_vbt_csv(path: Path) -> bool:
    """True when a .csv carries the VBT columns (exercise, load, velocity, reps)."""
    columns, _ = _read_csv_rows(path)
    return all(
        _pick(columns, group) is not None
        for group in (_EXERCISE_COLUMNS, _LOAD_COLUMNS, _VELOCITY_COLUMNS, _REPS_COLUMNS)
    )


def parse_vbt_csv(path: Path) -> list[VbtSet]:
    """Parse a VBT CSV export into VbtSet rows (exercise, load, velocity, reps).

    Maps common header variants; rows missing the exercise, load, velocity or reps,
    or carrying non-positive values, are skipped. Raises ActivityImportError when
    the required columns are absent or no row is usable.
    """
    columns, rows = _read_csv_rows(path)
    exercise_col = _pick(columns, _EXERCISE_COLUMNS)
    load_col = _pick(columns, _LOAD_COLUMNS)
    velocity_col = _pick(columns, _VELOCITY_COLUMNS)
    reps_col = _pick(columns, _REPS_COLUMNS)
    if not (exercise_col and load_col and velocity_col and reps_col):
        msg = (
            f"'{path.name}' is not a VBT export; needs exercise, load, velocity and reps "
            f"columns (got {columns})"
        )
        raise ActivityImportError(msg)
    top_col = _pick(columns, _TOP_VELOCITY_COLUMNS)
    sets = [
        _row_to_set(row, exercise_col, load_col, velocity_col, reps_col, top_col) for row in rows
    ]
    parsed = [item for item in sets if item is not None]
    if not parsed:
        msg = f"'{path.name}' had no rows with a valid exercise, load, velocity and reps"
        raise ActivityImportError(msg)
    return parsed


def _row_to_set(  # noqa: PLR0913 -- one resolved column per parameter
    row: dict[str, str],
    exercise_col: str,
    load_col: str,
    velocity_col: str,
    reps_col: str,
    top_col: str | None,
) -> VbtSet | None:
    exercise = row.get(exercise_col, "").strip()
    load = _to_float(row.get(load_col, ""))
    velocity = _to_float(row.get(velocity_col, ""))
    reps = _to_float(row.get(reps_col, ""))
    if not exercise or load is None or velocity is None or reps is None:
        return None
    if load < 0 or velocity <= 0 or reps < 1:
        return None
    top = _to_float(row.get(top_col, "")) if top_col else None
    return VbtSet(
        exercise=exercise,
        load_kg=load,
        mean_velocity=velocity,
        reps=int(reps),
        top_velocity=top if top is not None and top > 0 else None,
    )
