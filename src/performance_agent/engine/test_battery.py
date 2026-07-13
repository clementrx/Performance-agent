"""Test-battery scheduling: place KPI re-tests across a horizon (pure).

Tests are experiments: each quality has a re-test cadence (how often re-measuring
is informative), and a test is never scheduled inside a taper or on a competition
week (a blackout). The engine works in integer week space (week 1 = first planned
week); the memory layer resolves real dates and derives the blackout weeks from
the calendar. Deterministic and datetime-free.
"""

from dataclasses import dataclass

from performance_agent.engine._validation import validate_whole_number

# Re-test cadence in weeks per quality (team-chosen priors): fast-adapting
# qualities (speed, power) are worth re-checking more often than slow ones
# (aerobic base, mobility). Anything unlisted falls back to _DEFAULT_CADENCE.
_RETEST_CADENCE_WEEKS: dict[str, int] = {
    "max_strength": 6,
    "explosive_strength": 4,
    "reactive_strength": 4,
    "speed": 4,
    "acceleration": 4,
    "change_of_direction": 4,
    "aerobic_capacity": 8,
    "anaerobic_capacity": 6,
    "muscular_endurance": 6,
    "hypertrophy": 6,
    "mobility": 8,
    "balance_stability": 8,
}
_DEFAULT_CADENCE = 6


@dataclass(frozen=True)
class TestableKpi:
    """One KPI eligible for scheduling, with its quality and whether it needs a baseline."""

    __test__ = False  # not a pytest test class despite the Test* name

    kpi_id: str
    quality: str
    needs_baseline: bool


@dataclass(frozen=True)
class ScheduledTest:
    """A KPI re-test placed on a week (kind = baseline or re-test)."""

    week: int
    kpi_id: str
    quality: str
    kind: str


def cadence_for(quality: str) -> int:
    """Return the re-test cadence in weeks for a quality (team-chosen prior)."""
    return _RETEST_CADENCE_WEEKS.get(quality, _DEFAULT_CADENCE)


def _first_free_week_at_or_before(week: int, blackout: frozenset[int]) -> int | None:
    """Nearest week <= `week` (and >= 1) that is not a blackout, else None."""
    candidate = week
    while candidate >= 1:
        if candidate not in blackout:
            return candidate
        candidate -= 1
    return None


def _schedule_one(
    kpi: TestableKpi, horizon_weeks: int, blackout: frozenset[int]
) -> list[ScheduledTest]:
    cadence = cadence_for(kpi.quality)
    placed: dict[int, ScheduledTest] = {}
    if kpi.needs_baseline:
        week = _first_free_week_at_or_before(1, blackout)
        # A baseline can only shift earlier; if week 1 is blacked out there is no
        # earlier week, so a baseline that cannot be placed is simply dropped.
        if week is not None and week not in blackout:
            placed[week] = ScheduledTest(week, kpi.kpi_id, kpi.quality, "baseline")
    target = cadence
    while target <= horizon_weeks:
        week = _first_free_week_at_or_before(target, blackout)
        if week is not None and week not in placed:
            placed[week] = ScheduledTest(week, kpi.kpi_id, kpi.quality, "retest")
        target += cadence
    return list(placed.values())


def plan_test_battery(
    kpis: list[TestableKpi], horizon_weeks: int, blackout_weeks: frozenset[int]
) -> list[ScheduledTest]:
    """Schedule baseline + cadence-based re-tests for each KPI across the horizon.

    Each KPI marked `needs_baseline` gets a week-1 baseline (shifted earlier only,
    dropped if week 1 is a blackout); re-tests land at multiples of the quality's
    cadence, each shifted to the nearest earlier non-blackout week. Tests are never
    placed on a blackout week (taper or competition). Returns the schedule sorted
    by (week, kpi_id); deterministic.
    """
    validate_whole_number("horizon_weeks", horizon_weeks)
    if horizon_weeks < 1:
        msg = f"horizon_weeks must be >= 1, got {horizon_weeks!r}"
        raise ValueError(msg)
    for week in blackout_weeks:
        validate_whole_number("blackout_week", week)
    tests: list[ScheduledTest] = []
    for kpi in kpis:
        tests.extend(_schedule_one(kpi, horizon_weeks, blackout_weeks))
    tests.sort(key=lambda t: (t.week, t.kpi_id))
    return tests
