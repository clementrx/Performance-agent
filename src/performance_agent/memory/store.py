"""Read/write operations for the athlete data directory.

All writes are atomic (temp file + os.replace) and schema-validated. The store
never deletes history: logs are append-only and program versions are immutable.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.documents import ensure_documentation_dir
from performance_agent.memory.schemas import (
    Calendar,
    CalendarEvent,
    CheckinEntry,
    CompetitionProtocol,
    ExerciseLibrary,
    Goal,
    KpiResult,
    MacroPlan,
    PerformanceModel,
    Profile,
    ProgramPlan,
    ReadinessEntry,
    RecurringConstraint,
    ResponseProfile,
    SessionAdjustmentEntry,
    SessionEntry,
    SessionPlan,
)
from performance_agent.programs.render import render_program
from performance_agent.programs.render_protocol import render_protocol

PROFILE_FILE = "profile.yaml"
GOALS_FILE = "goals.yaml"
CALENDAR_FILE = "calendar.yaml"
SESSIONS_FILE = "sessions.jsonl"
CHECKINS_FILE = "checkins.jsonl"
READINESS_FILE = "readiness.jsonl"
SESSION_ADJUSTMENTS_FILE = "session_adjustments.jsonl"
KPI_RESULTS_FILE = "kpi_results.jsonl"
PROGRAMS_DIR = "programs"
ANALYSIS_DIR = "analysis"
RESEARCH_DIR = "research"
NUTRITION_DIR = "nutrition"
RESPONSE_DIR = "response"
RESPONSE_PREFIX = "response-profile"
MODELS_DIR = "models"
PERFORMANCE_MODEL_PREFIX = "performance-model"
MACRO_DIR = "macro"
MACRO_PLAN_PREFIX = "macro-plan"
EXERCISES_DIR = "exercises"
EXERCISE_LIBRARY_FILE = "library.yaml"
WATCH_DIR = "watch"
COMPETITION_DIR = "competition"
_FRONTMATTER_DELIMITER = "---\n"
_FRONTMATTER_DELIMITER_COUNT = 2


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _to_yaml(data: object) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _parse_yaml(text: str, path: Path) -> object:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"{path} contains invalid YAML: {exc}"
        raise ValueError(msg) from exc


def _load_yaml(path: Path) -> object:
    return _parse_yaml(path.read_text(encoding="utf-8"), path)


def _validated[T](path: Path, parse: Callable[[], T]) -> T:
    try:
        return parse()
    except ValidationError as exc:
        msg = f"{path} contains data that violates the schema: {exc}"
        raise ValueError(msg) from exc


def read_profile(base_dir: Path) -> Profile:
    """Return the stored profile, or a default Profile when none exists."""
    path = base_dir / PROFILE_FILE
    if not path.exists():
        return Profile()
    return _validated(path, lambda: Profile.model_validate(_load_yaml(path) or {}))


def write_profile(base_dir: Path, profile: Profile) -> Path:
    """Persist the profile as readable YAML; returns the file path.

    Also bootstraps the documentation/ drop folder so onboarding creates it.
    """
    path = base_dir / PROFILE_FILE
    _atomic_write(path, _to_yaml(profile.model_dump(mode="json")))
    ensure_documentation_dir(base_dir)
    return path


def read_goals(base_dir: Path) -> list[Goal]:
    """Return all stored goals (empty list when the file is missing)."""
    path = base_dir / GOALS_FILE
    if not path.exists():
        return []
    raw = _load_yaml(path) or []
    if not isinstance(raw, list):
        msg = f"{path} must contain a YAML list of goals (each item starting with '- ')"
        raise ValueError(msg)
    return _validated(path, lambda: [Goal.model_validate(item) for item in raw])


def upsert_goal(base_dir: Path, goal: Goal) -> list[Goal]:
    """Add a goal or replace the one with the same id; returns the updated list."""
    goals = [g for g in read_goals(base_dir) if g.id != goal.id]
    goals.append(goal)
    _atomic_write(
        base_dir / GOALS_FILE,
        _to_yaml([g.model_dump(mode="json") for g in goals]),
    )
    return goals


def read_calendar(base_dir: Path) -> Calendar:
    """Return the stored season calendar, or an empty one when none exists."""
    path = base_dir / CALENDAR_FILE
    if not path.exists():
        return Calendar()
    return _validated(path, lambda: Calendar.model_validate(_load_yaml(path) or {}))


def write_calendar(base_dir: Path, calendar: Calendar) -> Path:
    """Persist the whole calendar as readable YAML; returns the file path."""
    path = base_dir / CALENDAR_FILE
    _atomic_write(path, _to_yaml(calendar.model_dump(mode="json")))
    return path


def upsert_calendar_event(base_dir: Path, event: CalendarEvent) -> Calendar:
    """Add a dated event or replace the one with the same id; events stay date-sorted."""
    calendar = read_calendar(base_dir)
    events = [e for e in calendar.events if e.id != event.id]
    events.append(event)
    events.sort(key=lambda e: e.date)
    updated = calendar.model_copy(update={"events": events})
    write_calendar(base_dir, updated)
    return updated


def remove_calendar_event(base_dir: Path, event_id: str) -> Calendar:
    """Remove the dated event with this id (no-op when absent)."""
    calendar = read_calendar(base_dir)
    events = [e for e in calendar.events if e.id != event_id]
    updated = calendar.model_copy(update={"events": events})
    write_calendar(base_dir, updated)
    return updated


def set_recurring_constraints(base_dir: Path, recurring: list[RecurringConstraint]) -> Calendar:
    """Replace the whole recurring-constraint list (whole-list replace, not merge)."""
    calendar = read_calendar(base_dir)
    updated = calendar.model_copy(update={"recurring": list(recurring)})
    write_calendar(base_dir, updated)
    return updated


def _append_jsonl(path: Path, json_line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json_line + "\n")


def append_session(base_dir: Path, entry: SessionEntry) -> None:
    """Append one completed session to the append-only log."""
    _append_jsonl(base_dir / SESSIONS_FILE, entry.model_dump_json())


def read_sessions(base_dir: Path) -> list[SessionEntry]:
    """Return all logged sessions in insertion order."""
    path = base_dir / SESSIONS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [SessionEntry.model_validate_json(line) for line in lines if line.strip()],
    )


def append_checkin(base_dir: Path, entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; fills days_since_last from the previous one when unset.

    days_since_last may be negative for backdated entries.
    """
    previous = read_checkins(base_dir)
    if entry.days_since_last is None and previous:
        entry = entry.model_copy(update={"days_since_last": (entry.at - previous[-1].at).days})
    _append_jsonl(base_dir / CHECKINS_FILE, entry.model_dump_json())
    return entry


def read_checkins(base_dir: Path) -> list[CheckinEntry]:
    """Return all logged check-ins in insertion order."""
    path = base_dir / CHECKINS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [CheckinEntry.model_validate_json(line) for line in lines if line.strip()],
    )


def append_readiness(base_dir: Path, entry: ReadinessEntry) -> None:
    """Append one pre-session readiness read to the append-only log."""
    _append_jsonl(base_dir / READINESS_FILE, entry.model_dump_json())


def read_readiness(base_dir: Path) -> list[ReadinessEntry]:
    """Return all logged readiness reads in insertion order."""
    path = base_dir / READINESS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [ReadinessEntry.model_validate_json(line) for line in lines if line.strip()],
    )


def append_session_adjustment(base_dir: Path, entry: SessionAdjustmentEntry) -> None:
    """Append one day-of session adjustment to the append-only log."""
    _append_jsonl(base_dir / SESSION_ADJUSTMENTS_FILE, entry.model_dump_json())


def read_session_adjustments(base_dir: Path) -> list[SessionAdjustmentEntry]:
    """Return all logged session adjustments in insertion order."""
    path = base_dir / SESSION_ADJUSTMENTS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [
            SessionAdjustmentEntry.model_validate_json(line) for line in lines if line.strip()
        ],
    )


def read_exercise_library(base_dir: Path) -> ExerciseLibrary:
    """Return the athlete's added-exercise library, or an empty one when none exists."""
    path = base_dir / EXERCISES_DIR / EXERCISE_LIBRARY_FILE
    if not path.exists():
        return ExerciseLibrary()
    return _validated(path, lambda: ExerciseLibrary.model_validate(_load_yaml(path) or {}))


def write_exercise_library(base_dir: Path, library: ExerciseLibrary) -> Path:
    """Persist the whole athlete exercise library as readable YAML; returns the path."""
    path = base_dir / EXERCISES_DIR / EXERCISE_LIBRARY_FILE
    _atomic_write(path, _to_yaml(library.model_dump(mode="json")))
    return path


def append_kpi_result(base_dir: Path, entry: KpiResult) -> None:
    """Append one dated KPI/test measurement to the append-only log."""
    _append_jsonl(base_dir / KPI_RESULTS_FILE, entry.model_dump_json())


def read_kpi_results(base_dir: Path) -> list[KpiResult]:
    """Return all logged KPI results in insertion order."""
    path = base_dir / KPI_RESULTS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [KpiResult.model_validate_json(line) for line in lines if line.strip()],
    )


def find_session_plan(base_dir: Path, session_plan_id: str) -> SessionPlan | None:
    """Locate a SessionPlan by id in the latest structured program (None if absent)."""
    program = read_program(base_dir)
    if program is None or program.plan is None:
        return None
    for meso in program.plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                if session.id == session_plan_id:
                    return session
    return None


def _doc_path(base_dir: Path, subdir: str, prefix: str, version: int, suffix: str = ".md") -> Path:
    return base_dir / subdir / f"{prefix}-v{version}{suffix}"


def _latest_doc_version(
    base_dir: Path, subdir: str, prefix: str, suffix: str = ".md"
) -> int | None:
    doc_dir = base_dir / subdir
    if not doc_dir.is_dir():
        return None
    marker = f"{prefix}-v"
    # Path.stem drops only the final suffix; ".plan.yaml" would leave ".plan",
    # so strip the full suffix off the name explicitly before parsing the int.
    versions = [
        int(stem)
        for path in doc_dir.glob(f"{marker}*{suffix}")
        if (stem := path.name.removeprefix(marker).removesuffix(suffix)).isdigit()
        and str(int(stem)) == stem
    ]
    return max(versions) if versions else None


def _save_versioned_doc(  # noqa: PLR0913 -- shared by 3 doc families, all keyword-only past 3
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    *,
    subdir: str,
    prefix: str,
    label: str,
    reason: str | None,
    today: date | None,
) -> tuple[Path, int]:
    current = _latest_doc_version(base_dir, subdir, prefix)
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting {label} v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    frontmatter = {
        "version": version,
        "goal_id": goal_id,
        "created_on": (today or date.today()).isoformat(),
        "reason": reason,
    }
    content = "---\n" + _to_yaml(frontmatter) + "---\n\n" + markdown_body.strip() + "\n"
    path = _doc_path(base_dir, subdir, prefix, version)
    if path.exists():
        msg = f"{path} already exists; {label} versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, content)
    return path, version


def _split_frontmatter(path: Path, text: str) -> tuple[dict[str, object], str]:
    if text.count(_FRONTMATTER_DELIMITER) < _FRONTMATTER_DELIMITER_COUNT:
        msg = f"{path} is missing YAML frontmatter delimited by '---' lines"
        raise ValueError(msg)
    _, frontmatter_text, body = text.split(_FRONTMATTER_DELIMITER, 2)
    raw = _parse_yaml(frontmatter_text, path)
    if not isinstance(raw, dict):
        msg = f"{path} frontmatter must be a YAML mapping"
        raise ValueError(msg)
    return {str(key): value for key, value in raw.items()}, body.strip()


def _read_versioned_doc(
    base_dir: Path,
    *,
    subdir: str,
    prefix: str,
    label: str,
    version: int | None,
) -> tuple[dict[str, object], str] | None:
    target = version if version is not None else _latest_doc_version(base_dir, subdir, prefix)
    if target is None:
        return None
    path = _doc_path(base_dir, subdir, prefix, target)
    if not path.exists():
        msg = f"{label} version {target} does not exist"
        raise ValueError(msg)
    frontmatter, body = _split_frontmatter(path, path.read_text(encoding="utf-8"))
    if frontmatter.get("version") != target:
        msg = (
            f"{path} frontmatter declares version {frontmatter.get('version')} "
            f"but the filename says {target}"
        )
        raise ValueError(msg)
    return frontmatter, body


def _program_md_index(base_dir: Path) -> dict[int, Path]:
    """Map each stored program version to its markdown file.

    The version lives in the frontmatter, not the filename: programs are named
    program-YYYYMMDD[-K].md (K disambiguates same-day versions) since 0.7.0,
    and program-vN.md before — both stay readable through this index.
    """
    doc_dir = base_dir / PROGRAMS_DIR
    if not doc_dir.is_dir():
        return {}
    index: dict[int, Path] = {}
    for path in sorted(doc_dir.glob("program-*.md")):
        frontmatter, _ = _split_frontmatter(path, path.read_text(encoding="utf-8"))
        version = frontmatter.get("version")
        if not isinstance(version, int):
            msg = f"{path} frontmatter must declare an integer version"
            raise ValueError(msg)
        if version in index:
            msg = (
                f"program version {version} is declared by both "
                f"{index[version].name} and {path.name}"
            )
            raise ValueError(msg)
        index[version] = path
    return index


def latest_program_version(base_dir: Path) -> int | None:
    """Return the highest existing program version, or None."""
    index = _program_md_index(base_dir)
    return max(index) if index else None


def latest_analysis_version(base_dir: Path) -> int | None:
    """Return the highest existing needs-analysis version, or None."""
    return _latest_doc_version(base_dir, ANALYSIS_DIR, "needs-analysis")


def latest_research_dossier_version(base_dir: Path) -> int | None:
    """Return the highest existing research-dossier version, or None."""
    return _latest_doc_version(base_dir, RESEARCH_DIR, "dossier")


def latest_nutrition_frame_version(base_dir: Path) -> int | None:
    """Return the highest existing nutrition-frame version, or None."""
    return _latest_doc_version(base_dir, NUTRITION_DIR, "frame")


@dataclass(frozen=True)
class ProgramRead:
    """A stored program version: rendered markdown plus its structured plan.

    plan is None for legacy prose-only versions saved before the structured
    format landed; those stay readable and adaptable forever.
    """

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    plan: ProgramPlan | None


def _plan_yaml_path(md_path: Path) -> Path:
    return md_path.with_name(md_path.name.removesuffix(".md") + ".plan.yaml")


def _program_paths(base_dir: Path, created: date) -> tuple[Path, Path]:
    """Return fresh (md, plan.yaml) paths named after the creation date.

    program-YYYYMMDD; a second version the same day gets -2, then -3, etc.
    """
    programs = base_dir / PROGRAMS_DIR
    base = f"program-{created:%Y%m%d}"
    name = base
    counter = 2
    while (programs / f"{name}.md").exists() or (programs / f"{name}.plan.yaml").exists():
        name = f"{base}-{counter}"
        counter += 1
    return programs / f"{name}.md", programs / f"{name}.plan.yaml"


def save_program(
    base_dir: Path,
    plan: ProgramPlan,
    reason: str | None = None,
    today: date | None = None,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> tuple[Path, int]:
    """Validate, render, and atomically write a program as a yaml+md pair.

    Files are named after the creation date (program-YYYYMMDD.md, -2/-3 on
    same-day versions); the version number lives in the frontmatter and the
    plan yaml, which stays the source of truth so the markdown can never
    drift. Versions are immutable and never overwritten; adapting an existing
    program (v2+) requires a reason (the coaching-decision audit trail). The
    store owns version numbering — the plan's version/created_on/reason are
    stamped here. citations maps the plan's corpus ids to their resolved
    rendering; the server resolves them — None keeps the legacy citation-less
    rendering for direct store users.
    """
    current = latest_program_version(base_dir)
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting program v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    created = today or date.today()
    stamped = plan.model_copy(update={"version": version, "reason": reason, "created_on": created})
    md_path, yaml_path = _program_paths(base_dir, created)
    frontmatter = {
        "version": version,
        "goal_id": stamped.goal_id,
        "created_on": created.isoformat(),
        "reason": reason,
    }
    content = (
        "---\n"
        + _to_yaml(frontmatter)
        + "---\n\n"
        + render_program(stamped, citations=citations).strip()
        + "\n"
    )
    _atomic_write(yaml_path, _to_yaml(stamped.model_dump(mode="json")))
    try:
        _atomic_write(md_path, content)
    except OSError:
        yaml_path.unlink(missing_ok=True)
        raise
    return md_path, version


def read_program(base_dir: Path, version: int | None = None) -> ProgramRead | None:
    """Return the given or latest program version, or None when none exists.

    The structured plan is included when present; it is None for legacy
    prose-only versions.
    """
    index = _program_md_index(base_dir)
    target = version if version is not None else (max(index) if index else None)
    if target is None:
        return None
    if target not in index:
        msg = f"program version {target} does not exist"
        raise ValueError(msg)
    md_path = index[target]
    frontmatter, body = _split_frontmatter(md_path, md_path.read_text(encoding="utf-8"))
    resolved = int(str(frontmatter["version"]))
    yaml_path = _plan_yaml_path(md_path)
    plan: ProgramPlan | None = None
    if yaml_path.exists():
        raw = _load_yaml(yaml_path)
        plan = _validated(yaml_path, lambda: ProgramPlan.model_validate(raw))
    reason = frontmatter.get("reason")
    return ProgramRead(
        version=resolved,
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(reason) if reason is not None else None,
        markdown=body,
        plan=plan,
    )


def latest_response_profile_version(base_dir: Path) -> int | None:
    """Return the highest existing response-profile version, or None."""
    return _latest_doc_version(base_dir, RESPONSE_DIR, RESPONSE_PREFIX, suffix=".yaml")


def save_response_profile(
    base_dir: Path,
    profile: ResponseProfile,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next response-profile version as immutable YAML.

    Same immutable-version audit trail as programs, but the payload is a YAML
    ResponseProfile document (not markdown-with-frontmatter): versions are never
    overwritten and every revision (v2+) requires a reason. The store stamps the
    authoritative version, as_of date and reason onto the profile.
    """
    current = _latest_doc_version(base_dir, RESPONSE_DIR, RESPONSE_PREFIX, suffix=".yaml")
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting response profile v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    stamped = profile.model_copy(
        update={"version": version, "reason": reason, "as_of": today or date.today()}
    )
    path = _doc_path(base_dir, RESPONSE_DIR, RESPONSE_PREFIX, version, suffix=".yaml")
    if path.exists():
        msg = f"{path} already exists; response profile versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, _to_yaml(stamped.model_dump(mode="json")))
    return path, version


def read_response_profile(base_dir: Path, version: int | None = None) -> ResponseProfile | None:
    """Return the given or latest response profile, or None when none exists."""
    target = (
        version
        if version is not None
        else _latest_doc_version(base_dir, RESPONSE_DIR, RESPONSE_PREFIX, suffix=".yaml")
    )
    if target is None:
        return None
    path = _doc_path(base_dir, RESPONSE_DIR, RESPONSE_PREFIX, target, suffix=".yaml")
    if not path.exists():
        msg = f"response profile version {target} does not exist"
        raise ValueError(msg)
    raw = _load_yaml(path)
    return _validated(path, lambda: ResponseProfile.model_validate(raw))


def latest_performance_model_version(base_dir: Path) -> int | None:
    """Return the highest existing performance-model version, or None."""
    return _latest_doc_version(base_dir, MODELS_DIR, PERFORMANCE_MODEL_PREFIX, suffix=".yaml")


def save_performance_model(
    base_dir: Path,
    model: PerformanceModel,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next performance-model version as immutable YAML.

    Same immutable-version audit trail as programs and response profiles: the
    payload is a YAML PerformanceModel document, versions are never overwritten,
    and every revision (v2+) requires a reason. The store stamps the
    authoritative version and reason onto the model. today is accepted for
    signature parity with the other versioned stores (the model carries no date).
    """
    _ = today
    current = _latest_doc_version(base_dir, MODELS_DIR, PERFORMANCE_MODEL_PREFIX, suffix=".yaml")
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting performance model v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    stamped = model.model_copy(update={"version": version, "reason": reason})
    path = _doc_path(base_dir, MODELS_DIR, PERFORMANCE_MODEL_PREFIX, version, suffix=".yaml")
    if path.exists():
        msg = f"{path} already exists; performance model versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, _to_yaml(stamped.model_dump(mode="json")))
    return path, version


def read_performance_model(base_dir: Path, version: int | None = None) -> PerformanceModel | None:
    """Return the given or latest performance model, or None when none exists."""
    target = (
        version
        if version is not None
        else _latest_doc_version(base_dir, MODELS_DIR, PERFORMANCE_MODEL_PREFIX, suffix=".yaml")
    )
    if target is None:
        return None
    path = _doc_path(base_dir, MODELS_DIR, PERFORMANCE_MODEL_PREFIX, target, suffix=".yaml")
    if not path.exists():
        msg = f"performance model version {target} does not exist"
        raise ValueError(msg)
    raw = _load_yaml(path)
    return _validated(path, lambda: PerformanceModel.model_validate(raw))


def latest_macro_plan_version(base_dir: Path) -> int | None:
    """Return the highest existing macro-plan version, or None."""
    return _latest_doc_version(base_dir, MACRO_DIR, MACRO_PLAN_PREFIX, suffix=".yaml")


def save_macro_plan(
    base_dir: Path,
    plan: MacroPlan,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next macro-plan version as immutable YAML (reason from v2)."""
    _ = today
    current = _latest_doc_version(base_dir, MACRO_DIR, MACRO_PLAN_PREFIX, suffix=".yaml")
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting macro plan v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    stamped = plan.model_copy(update={"version": version, "reason": reason})
    path = _doc_path(base_dir, MACRO_DIR, MACRO_PLAN_PREFIX, version, suffix=".yaml")
    if path.exists():
        msg = f"{path} already exists; macro plan versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, _to_yaml(stamped.model_dump(mode="json")))
    return path, version


def read_macro_plan(base_dir: Path, version: int | None = None) -> MacroPlan | None:
    """Return the given or latest macro plan, or None when none exists."""
    target = (
        version
        if version is not None
        else _latest_doc_version(base_dir, MACRO_DIR, MACRO_PLAN_PREFIX, suffix=".yaml")
    )
    if target is None:
        return None
    path = _doc_path(base_dir, MACRO_DIR, MACRO_PLAN_PREFIX, target, suffix=".yaml")
    if not path.exists():
        msg = f"macro plan version {target} does not exist"
        raise ValueError(msg)
    raw = _load_yaml(path)
    return _validated(path, lambda: MacroPlan.model_validate(raw))


def save_analysis(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next needs-analysis version; revising an existing one requires a reason.

    Same immutable-version audit trail as programs; lives in analysis/.
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=ANALYSIS_DIR,
        prefix="needs-analysis",
        label="needs analysis",
        reason=reason,
        today=today,
    )


def read_analysis(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest needs analysis; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=ANALYSIS_DIR,
        prefix="needs-analysis",
        label="needs analysis",
        version=version,
    )


def save_research_dossier(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next research-dossier version; re-research requires a reason.

    Same immutable-version audit trail as programs; lives in research/.
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=RESEARCH_DIR,
        prefix="dossier",
        label="research dossier",
        reason=reason,
        today=today,
    )


def read_research_dossier(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest dossier; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=RESEARCH_DIR,
        prefix="dossier",
        label="research dossier",
        version=version,
    )


def save_nutrition_frame(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next nutrition-frame version; recalculation requires a reason.

    Same immutable-version audit trail as programs; lives in nutrition/. The
    body is markdown with the engine-computed numbers in a fenced yaml block
    (store uniformity over the spec's frame-v1.yaml sketch — deliberate).
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=NUTRITION_DIR,
        prefix="frame",
        label="nutrition frame",
        reason=reason,
        today=today,
    )


def read_nutrition_frame(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest frame; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=NUTRITION_DIR,
        prefix="frame",
        label="nutrition frame",
        version=version,
    )


def latest_watch_report_version(base_dir: Path) -> int | None:
    """Return the highest existing watch-report version, or None."""
    return _latest_doc_version(base_dir, WATCH_DIR, "report")


def save_watch_report(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next program-watch report version; v2+ requires a reason.

    Same immutable-version audit trail as the other doc families; lives in
    watch/. The latest report's created_on is also the diligence anchor for
    "program watch due".
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=WATCH_DIR,
        prefix="report",
        label="watch report",
        reason=reason,
        today=today,
    )


def read_watch_report(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest watch report; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=WATCH_DIR,
        prefix="report",
        label="watch report",
        version=version,
    )


@dataclass(frozen=True)
class ProtocolRead:
    """A stored competition-protocol version: structured plan plus its markdown."""

    version: int
    event_id: str
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    protocol: CompetitionProtocol


def _protocol_prefix(event_id: str) -> str:
    return f"protocol-{event_id}"


def latest_competition_protocol_version(base_dir: Path, event_id: str) -> int | None:
    """Highest stored protocol version for this event, or None."""
    return _latest_doc_version(base_dir, COMPETITION_DIR, _protocol_prefix(event_id))


def _validate_calendar_event(base_dir: Path, protocol: CompetitionProtocol, current: date) -> None:
    event = next((e for e in read_calendar(base_dir).events if e.id == protocol.event_id), None)
    if event is None:
        msg = f"event {protocol.event_id!r} is not in the calendar; add it first"
        raise ValueError(msg)
    if event.date != protocol.event_date:
        msg = (
            f"protocol event_date {protocol.event_date} does not match the calendar "
            f"date {event.date} for {protocol.event_id!r}"
        )
        raise ValueError(msg)
    if event.date < current:
        msg = f"event {protocol.event_id!r} ({event.date}) is in the past"
        raise ValueError(msg)


def save_competition_protocol(
    base_dir: Path,
    protocol: CompetitionProtocol,
    reason: str | None = None,
    today: date | None = None,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> tuple[Path, int]:
    """Validate against the calendar and write the next protocol version.

    The event must exist in calendar.yaml with the same date (a rescheduled
    event needs a v2 with a reason, never a silent drift) and must not be in
    the past. yaml is the source of truth, markdown the rendered view; both
    are immutable once written. citations maps corpus ids to their resolved
    rendering (the server resolves them; None keeps a citation-less render).
    """
    current = today or date.today()
    _validate_calendar_event(base_dir, protocol, current)
    prefix = _protocol_prefix(protocol.event_id)
    latest = latest_competition_protocol_version(base_dir, protocol.event_id)
    version = 1 if latest is None else latest + 1
    if version > 1 and not reason:
        msg = (
            f"adapting protocol v{latest} to v{version} for {protocol.event_id!r} "
            "requires a reason (audit trail)"
        )
        raise ValueError(msg)
    stamped = protocol.model_copy(
        update={"version": version, "reason": reason, "created_on": current}
    )
    frontmatter = {
        "version": version,
        "event_id": stamped.event_id,
        "goal_id": stamped.goal_id,
        "created_on": current.isoformat(),
        "reason": reason,
    }
    md_path = base_dir / COMPETITION_DIR / f"{prefix}-v{version}.md"
    yaml_path = md_path.with_suffix(".yaml")
    content = (
        "---\n"
        + _to_yaml(frontmatter)
        + "---\n\n"
        + render_protocol(stamped, citations=citations).strip()
        + "\n"
    )
    _atomic_write(yaml_path, _to_yaml(stamped.model_dump(mode="json")))
    try:
        _atomic_write(md_path, content)
    except OSError:
        yaml_path.unlink(missing_ok=True)
        raise
    return md_path, version


def _validate_stored_protocol(
    md_path: Path,
    frontmatter: Mapping[str, object],
    protocol: CompetitionProtocol,
    event_id: str,
    target: int,
) -> None:
    yaml_path = md_path.with_suffix(".yaml")
    if frontmatter.get("version") != target:
        msg = (
            f"{md_path} frontmatter declares version {frontmatter.get('version')} "
            f"but the filename says {target}"
        )
        raise ValueError(msg)
    if protocol.event_id != event_id:
        msg = (
            f"{yaml_path} declares event_id {protocol.event_id!r} "
            f"but was read for event_id {event_id!r}"
        )
        raise ValueError(msg)
    if protocol.version != target:
        msg = f"{yaml_path} declares version {protocol.version} but the filename says {target}"
        raise ValueError(msg)


def read_competition_protocol(
    base_dir: Path, event_id: str, version: int | None = None
) -> ProtocolRead | None:
    """Return the given or latest protocol for an event; None when none exists."""
    target = (
        version if version is not None else latest_competition_protocol_version(base_dir, event_id)
    )
    if target is None:
        return None
    prefix = _protocol_prefix(event_id)
    md_path = base_dir / COMPETITION_DIR / f"{prefix}-v{target}.md"
    yaml_path = md_path.with_suffix(".yaml")
    if not md_path.exists() or not yaml_path.exists():
        msg = f"protocol v{target} for {event_id!r} does not exist"
        raise ValueError(msg)
    frontmatter, markdown = _split_frontmatter(md_path, md_path.read_text(encoding="utf-8"))
    protocol = _validated(
        yaml_path,
        lambda: CompetitionProtocol.model_validate(_load_yaml(yaml_path) or {}),
    )
    _validate_stored_protocol(md_path, frontmatter, protocol, event_id, target)
    return ProtocolRead(
        version=target,
        event_id=event_id,
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(frontmatter["reason"]) if frontmatter.get("reason") is not None else None,
        markdown=markdown,
        protocol=protocol,
    )
