"""Session plausibility at the athlete layer: read history, call the engine guard.

The engine's flag_implausible_session is pure and numeric; this module extracts
the numbers it needs (best estimated 1RM per lift, known 1RM from the profile,
recent median duration) from the athlete's stored history and returns the flags
for a freshly logged session. Flags never block a write — the entry is logged
either way; the coach confirms flagged values with the athlete.
"""

from statistics import median
from typing import TypedDict

from performance_agent.engine import flag_implausible_session, one_rm_epley
from performance_agent.engine.strength import MAX_ESTIMATION_REPS
from performance_agent.memory.schemas import ExercisePerformed, Profile, SessionEntry

_RECENT_SESSION_WINDOW = 30  # sessions of history the guards look back over


class PlausibilityFlag(TypedDict):
    """One data-quality concern the coach must confirm before trusting the value."""

    code: str
    message: str


def _normalize(name: str) -> str:
    return name.strip().casefold()


def _best_set_e1rm(exercise: ExercisePerformed) -> tuple[float, float] | None:
    """Return (best_e1rm_kg, heaviest_load_kg) across an exercise's scored sets."""
    e1rms: list[float] = []
    loads: list[float] = []
    for performed in exercise.sets:
        if performed.load_kg > 0 and 1 <= performed.reps <= MAX_ESTIMATION_REPS:
            e1rms.append(one_rm_epley(performed.load_kg, performed.reps))
            loads.append(performed.load_kg)
    if not e1rms:
        return None
    return max(e1rms), max(loads)


def _recent_best_e1rm(history: list[SessionEntry], lift: str) -> float | None:
    target = _normalize(lift)
    best: float | None = None
    for entry in history[-_RECENT_SESSION_WINDOW:]:
        for exercise in entry.exercises:
            if _normalize(exercise.name) != target:
                continue
            scored = _best_set_e1rm(exercise)
            if scored is not None:
                best = scored[0] if best is None else max(best, scored[0])
    return best


def _known_1rm(profile: Profile, lift: str) -> float | None:
    target = _normalize(lift)
    matches = [r.one_rm_kg for r in profile.lift_inventory if _normalize(r.lift) == target]
    return max(matches) if matches else None


def _recent_median_duration(history: list[SessionEntry]) -> float | None:
    durations = [
        float(e.duration_min)
        for e in history[-_RECENT_SESSION_WINDOW:]
        if e.duration_min is not None
    ]
    return median(durations) if durations else None


def session_plausibility_flags(
    entry: SessionEntry, history: list[SessionEntry], profile: Profile
) -> list[PlausibilityFlag]:
    """Run the engine data-quality guards over a just-logged session entry.

    history is the log BEFORE this entry (so the entry is compared against its
    own past, not itself). Returns one flag per suspect value; empty when the
    session looks clean.
    """
    is_test = entry.kind is not None and "test" in entry.kind.casefold()
    median_duration = _recent_median_duration(history)
    flags: list[PlausibilityFlag] = []
    for exercise in entry.exercises:
        scored = _best_set_e1rm(exercise)
        if scored is None:
            continue
        session_e1rm, top_load = scored
        for flag in flag_implausible_session(
            session_e1rm_kg=session_e1rm,
            recent_best_e1rm_kg=_recent_best_e1rm(history, exercise.name),
            top_load_kg=top_load,
            known_1rm_kg=_known_1rm(profile, exercise.name),
            is_test=is_test,
        ):
            message = f"{exercise.name}: {flag.message}"
            flags.append(PlausibilityFlag(code=flag.code, message=message))
    for flag in flag_implausible_session(
        duration_min=float(entry.duration_min) if entry.duration_min is not None else None,
        median_duration_min=median_duration,
    ):
        flags.append(PlausibilityFlag(code=flag.code, message=flag.message))
    return flags
