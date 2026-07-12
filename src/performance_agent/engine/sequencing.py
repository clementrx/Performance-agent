"""Intra-week sequencing and interference guard (pure).

Encodes the order of the week -- the spacing, ordering and interference rules a
coach applies that a spreadsheet does not. Deterministic and datetime-free: the
engine works on lightweight engine-local dataclasses (SessionInput/RecurringInput)
because engine/ never imports memory.schemas (purity + no cycle). The memory layer
(memory/sequencing.py) converts a WeekPlan + list[RecurringConstraint] + the
athlete's available minutes into these inputs and maps the Violations back out.

Rules operate on the weekday field (0 = Monday). Sessions with no weekday cannot be
placed in the week and are skipped by every day-based rule -- the memory layer must
have the coach assign weekdays before a meaningful check is possible.

Every rule constant is a team-chosen prior / coaching judgment, labeled inline. The
interference rules (R1/R2) reflect the concurrent-training literature named in the
plan (Wilson et al. 2012 meta; Coffey & Hawley reviews), but those studies are NOT
in the evidence corpus, so no corpus id is claimed here -- the numeric thresholds
are coaching judgment, consistent with the repo's anti-fabrication rule.
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

Severity = Literal["block", "warn"]

# --- quality / pattern classes (team-chosen priors) -----------------------
# A "high" day taxes recovery: heavy lifting, high-intensity intervals, a match.
HIGH_QUALITIES = frozenset({"strength_heavy", "hiit", "match"})
# Strength stimulus that competes with endurance for the same-day ordering rule.
STRENGTH_QUALITIES = frozenset({"strength_heavy", "hypertrophy"})
# Aerobic/conditioning stimulus for the same-day ordering rule (hiit is R2's job).
ENDURANCE_QUALITIES = frozenset({"endurance_long", "endurance_easy", "tempo", "brick"})
# What may sit the day BEFORE a match: low CNS cost or short priming only.
PRIMING_QUALITIES = frozenset({"recovery", "endurance_easy", "power", "tempo"})
# What may sit the day AFTER a match: recovery / easy aerobic only.
POST_MATCH_QUALITIES = frozenset({"recovery", "endurance_easy"})
# Lower-body movement patterns -- the ones acute HIIT interference blunts most.
LOWER_PATTERNS = frozenset({"squat", "hinge", "lunge"})

# --- spacing / consecutive-day thresholds (team-chosen priors) ------------
# R1: >=48h between same-pattern heavy sessions; 72h in a high-volume week.
R1_MIN_GAP_DAYS = 2
R1_HIGH_VOLUME_GAP_DAYS = 3
R1_HIGH_VOLUME_FACTOR = 1.1
# R3: strength and endurance the same day want >=6h between them (narrated).
R3_MIN_GAP_HOURS = 6
# R4: at most two consecutive high days before recovery suffers.
MAX_CONSECUTIVE_HIGH_DAYS = 2

_MONDAY = 0
_SUNDAY = 6


@dataclass(frozen=True)
class SessionInput:
    """Engine-local view of one planned session, enough to sequence the week."""

    id: str
    weekday: int | None
    qualities: tuple[str, ...]
    patterns: tuple[str, ...]
    est_minutes: int


@dataclass(frozen=True)
class RecurringInput:
    """Engine-local view of one weekly recurring commitment (club/match/unavailable)."""

    weekday: int
    kind: str
    est_minutes: int | None


@dataclass(frozen=True)
class Violation:
    """One broken sequencing rule: block (must fix) or warn (acknowledge)."""

    rule_id: str
    severity: Severity
    session_ids: tuple[str, ...]
    message: str


def _validate_weekday(name: str, value: int) -> None:
    validate_whole_number(name, value)
    if value < _MONDAY or value > _SUNDAY:
        msg = f"{name} must be 0-6 (Mon-Sun), got {value!r}"
        raise ValueError(msg)


def _validate_inputs(
    sessions: list[SessionInput],
    recurring: list[RecurringInput],
    volume_factor: float,
    available_minutes: int | None,
) -> None:
    validate_finite("volume_factor", volume_factor)
    if volume_factor <= 0:
        msg = f"volume_factor must be > 0, got {volume_factor!r}"
        raise ValueError(msg)
    if available_minutes is not None:
        validate_whole_number("available_minutes", available_minutes)
        if available_minutes < 1:
            msg = f"available_minutes must be >= 1, got {available_minutes!r}"
            raise ValueError(msg)
    for session in sessions:
        if session.weekday is not None:
            _validate_weekday(f"session {session.id!r} weekday", session.weekday)
        validate_whole_number(f"session {session.id!r} est_minutes", session.est_minutes)
        if session.est_minutes < 1:
            msg = f"session {session.id!r} est_minutes must be >= 1, got {session.est_minutes!r}"
            raise ValueError(msg)
    for item in recurring:
        _validate_weekday("recurring weekday", item.weekday)


def _scheduled(sessions: list[SessionInput]) -> list[SessionInput]:
    return [s for s in sessions if s.weekday is not None]


def _by_weekday(sessions: list[SessionInput]) -> dict[int, list[SessionInput]]:
    grouped: dict[int, list[SessionInput]] = {}
    for session in sessions:
        if session.weekday is not None:
            grouped.setdefault(session.weekday, []).append(session)
    return grouped


def _has(session: SessionInput, qualities: frozenset[str]) -> bool:
    return any(q in qualities for q in session.qualities)


def _is_lower_strength(session: SessionInput) -> bool:
    return "strength_heavy" in session.qualities and any(
        p in LOWER_PATTERNS for p in session.patterns
    )


def _check_pattern_spacing(sessions: list[SessionInput], volume_factor: float) -> list[Violation]:
    """R1: keep same-pattern heavy sessions >=48h apart (72h in a high-volume week)."""
    min_gap = R1_HIGH_VOLUME_GAP_DAYS if volume_factor >= R1_HIGH_VOLUME_FACTOR else R1_MIN_GAP_DAYS
    hours = min_gap * 24
    heavy = [(s, s.weekday) for s in sessions if "strength_heavy" in s.qualities]
    heavy = [(s, wd) for s, wd in heavy if wd is not None]
    violations: list[Violation] = []
    for i, (first, wd1) in enumerate(heavy):
        for second, wd2 in heavy[i + 1 :]:
            shared = sorted(set(first.patterns) & set(second.patterns))
            if not shared:
                continue
            if wd1 is not None and wd2 is not None and abs(wd1 - wd2) < min_gap:
                violations.append(
                    Violation(
                        "R1",
                        "block",
                        tuple(sorted((first.id, second.id))),
                        f"two strength_heavy sessions load {shared} less than {hours}h apart; "
                        "space them out",
                    )
                )
    return violations


def _check_hiit_before_lower(sessions: list[SessionInput]) -> list[Violation]:
    """R2: no HIIT within 24h before a lower-body heavy day (acute interference)."""
    hiits = [(s, s.weekday) for s in sessions if "hiit" in s.qualities]
    lowers = [(s, s.weekday) for s in sessions if _is_lower_strength(s)]
    violations: list[Violation] = []
    for hiit, hiit_wd in hiits:
        for lower, lower_wd in lowers:
            if hiit_wd is not None and lower_wd is not None and lower_wd == hiit_wd + 1:
                violations.append(
                    Violation(
                        "R2",
                        "block",
                        tuple(sorted((hiit.id, lower.id))),
                        "HIIT sits the day before lower-body strength_heavy; the acute "
                        "interference blunts the heavy session -- move the HIIT",
                    )
                )
    return violations


def _check_same_day_order(
    by_day: dict[int, list[SessionInput]], strength_priority: bool
) -> list[Violation]:
    """R3: same-day strength + endurance -- strength first when it is the A goal."""
    if not strength_priority:
        return []
    violations: list[Violation] = []
    for _weekday, day_sessions in sorted(by_day.items()):
        has_strength = any(_has(s, STRENGTH_QUALITIES) for s in day_sessions)
        has_endurance = any(_has(s, ENDURANCE_QUALITIES) for s in day_sessions)
        if has_strength and has_endurance:
            violations.append(
                Violation(
                    "R3",
                    "warn",
                    tuple(sorted(s.id for s in day_sessions)),
                    "strength and endurance share a day; do strength first and aim for a "
                    f">={R3_MIN_GAP_HOURS}h gap (strength/hypertrophy is the A-priority goal)",
                )
            )
    return violations


def _high_weekdays(
    by_day: dict[int, list[SessionInput]], match_weekdays: frozenset[int]
) -> set[int]:
    days = {wd for wd, sess in by_day.items() if any(_has(s, HIGH_QUALITIES) for s in sess)}
    return days | set(match_weekdays)


def _consecutive_runs(days: set[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for day in sorted(days):
        if runs and day == runs[-1][-1] + 1:
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs


def _check_consecutive_high(
    by_day: dict[int, list[SessionInput]], match_weekdays: frozenset[int]
) -> list[Violation]:
    """R4: never more than two consecutive high days (heavy/HIIT/match)."""
    violations: list[Violation] = []
    for run in _consecutive_runs(_high_weekdays(by_day, match_weekdays)):
        if len(run) > MAX_CONSECUTIVE_HIGH_DAYS:
            ids = tuple(sorted(s.id for wd in run for s in by_day.get(wd, [])))
            violations.append(
                Violation(
                    "R4",
                    "block",
                    ids,
                    f"{len(run)} consecutive high days (weekdays {run}); insert a low or "
                    "recovery day so no more than two stack up",
                )
            )
    return violations


def _check_match_windows(
    by_day: dict[int, list[SessionInput]], match_weekdays: frozenset[int]
) -> list[Violation]:
    """R5: match day -1 = low/priming only; match day +1 = recovery/low."""
    violations: list[Violation] = []
    for match_day in sorted(match_weekdays):
        for session in by_day.get(match_day - 1, []):
            if not all(q in PRIMING_QUALITIES for q in session.qualities):
                violations.append(
                    Violation(
                        "R5",
                        "block",
                        (session.id,),
                        f"{session.id} sits the day before a match; keep it low/priming only",
                    )
                )
        for session in by_day.get(match_day + 1, []):
            if not all(q in POST_MATCH_QUALITIES for q in session.qualities):
                violations.append(
                    Violation(
                        "R5",
                        "block",
                        (session.id,),
                        f"{session.id} sits the day after a match; keep it recovery/low",
                    )
                )
    return violations


def _check_long_before_hard(
    sessions: list[SessionInput],
    by_day: dict[int, list[SessionInput]],
    match_weekdays: frozenset[int],
) -> list[Violation]:
    """R6: no endurance_long the day before a match or a key HIIT session."""
    violations: list[Violation] = []
    for session in sessions:
        if "endurance_long" not in session.qualities or session.weekday is None:
            continue
        next_day = session.weekday + 1
        hiit_next = sorted(s.id for s in by_day.get(next_day, []) if "hiit" in s.qualities)
        if next_day in match_weekdays or hiit_next:
            target = "a match" if next_day in match_weekdays else "a key HIIT session"
            violations.append(
                Violation(
                    "R6",
                    "warn",
                    tuple(sorted((session.id, *hiit_next))),
                    f"endurance_long sits the day before {target}; it arrives fatigued",
                )
            )
    return violations


def _day_minutes(
    day_sessions: list[SessionInput], recurring: list[RecurringInput], weekday: int
) -> int:
    total = sum(s.est_minutes for s in day_sessions)
    total += sum(r.est_minutes or 0 for r in recurring if r.weekday == weekday)
    return total


def _check_daily_minutes(
    by_day: dict[int, list[SessionInput]],
    recurring: list[RecurringInput],
    available_minutes: int | None,
) -> list[Violation]:
    """R7: a day's total planned minutes must fit the athlete's available time."""
    if available_minutes is None:
        return []
    violations: list[Violation] = []
    weekdays = set(by_day) | {r.weekday for r in recurring if r.est_minutes is not None}
    for weekday in sorted(weekdays):
        day_sessions = by_day.get(weekday, [])
        total = _day_minutes(day_sessions, recurring, weekday)
        if total > available_minutes:
            violations.append(
                Violation(
                    "R7",
                    "block",
                    tuple(sorted(s.id for s in day_sessions)),
                    f"weekday {weekday} totals {total} min of training vs "
                    f"{available_minutes} min available; trim the day",
                )
            )
    return violations


def check_week_sequencing(
    sessions: list[SessionInput],
    recurring: list[RecurringInput],
    *,
    volume_factor: float = 1.0,
    strength_priority: bool = False,
    available_minutes: int | None = None,
) -> list[Violation]:
    """Return every sequencing rule the week breaks (deterministic, sorted).

    Checks seven intra-week rules on the sessions' weekday field: same-pattern
    heavy spacing (R1), HIIT-before-lower interference (R2), same-day strength
    ordering (R3), consecutive high days (R4), the match day -1/+1 windows (R5),
    endurance_long before a hard day (R6), and per-day minutes vs available time
    (R7). Match weekdays come from recurring constraints with kind "match_day".
    Sessions without a weekday are skipped by every day-based rule. block
    violations must be fixed before delivery; warn violations must be acknowledged.
    """
    _validate_inputs(sessions, recurring, volume_factor, available_minutes)
    match_weekdays = frozenset(r.weekday for r in recurring if r.kind == "match_day")
    scheduled = _scheduled(sessions)
    by_day = _by_weekday(scheduled)
    violations: list[Violation] = []
    violations += _check_pattern_spacing(scheduled, volume_factor)
    violations += _check_hiit_before_lower(scheduled)
    violations += _check_same_day_order(by_day, strength_priority)
    violations += _check_consecutive_high(by_day, match_weekdays)
    violations += _check_match_windows(by_day, match_weekdays)
    violations += _check_long_before_hard(scheduled, by_day, match_weekdays)
    violations += _check_daily_minutes(by_day, recurring, available_minutes)
    return sorted(violations, key=lambda v: (v.rule_id, v.session_ids, v.message))
