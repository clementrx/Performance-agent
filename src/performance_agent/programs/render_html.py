"""Deterministic ProgramPlan -> standalone session HTML (the in-gym view).

Like the markdown renderer, the HTML is generated from the structured plan at
save time so it can never drift. The page is fully self-contained (inline CSS,
no external requests) and uses NO JavaScript: phone viewers such as iOS Quick
Look and in-app file previews don't run scripts. Exercise animation GIFs from
the exercises-dataset clone are embedded once each as base64 data URIs in CSS
background-image rules shared by class, so the file stays a few megabytes and
works offline on a phone at the gym. Media enrichment is best-effort: a block
that resolves to no dataset record renders its prescription without media
rather than with the wrong GIF.
"""

import html
import re

from performance_agent.engine import warmup_scheme
from performance_agent.exercises.dataset import DatasetExercise, ExerciseMediaIndex
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ProgramPlan,
    SessionPlan,
    WeekPlan,
)
from performance_agent.programs.render import intensity_label, num_label, volume_label

_LABELS = {
    "en": {
        "program": "Program",
        "week": "Week",
        "deload": "deload",
        "taper": "taper",
        "qualities": "Qualities",
        "patterns": "patterns",
        "warmup": "Warm-up",
        "warmup_judgment": "2-3 progressively heavier ramp sets to the working weight",
        "rest": "rest",
        "sets": "sets",
        "technique": "Technique",
        "equipment": "Equipment",
        "muscles": "Muscles",
        "fallbacks": "Fallbacks",
        "low_readiness": "Low readiness",
        "short_on_time": "Short on time",
        "missing_equipment": "Missing equipment",
        "test_milestones": "Test milestones",
        "checkin": "Check-in every {days} days",
        "reason": "Reason",
        "unscheduled": "unscheduled",
        "volume_intensity": "Volume x{volume}, intensity x{intensity}",
        "set_targets": "Weekly set targets",
        "media_credit": "Exercise media & instructions",
    },
    "fr": {
        "program": "Programme",
        "week": "Semaine",
        "deload": "décharge",
        "taper": "affûtage",
        "qualities": "Qualités",
        "patterns": "schémas moteurs",
        "warmup": "Échauffement",
        "warmup_judgment": "2-3 séries d'approche progressives jusqu'à la charge de travail",
        "rest": "repos",
        "sets": "séries",
        "technique": "Technique",
        "equipment": "Matériel",
        "muscles": "Muscles",
        "fallbacks": "Plans B",
        "low_readiness": "Fraîcheur basse",
        "short_on_time": "Peu de temps",
        "missing_equipment": "Matériel manquant",
        "test_milestones": "Jalons de test",
        "checkin": "Check-in tous les {days} jours",
        "reason": "Raison",
        "unscheduled": "non planifiée",
        "volume_intensity": "Volume x{volume}, intensité x{intensity}",
        "set_targets": "Cibles de séries hebdomadaires",
        "media_credit": "Médias & instructions des exercices",
    },
    "es": {
        "program": "Programa",
        "week": "Semana",
        "deload": "descarga",
        "taper": "puesta a punto",
        "qualities": "Cualidades",
        "patterns": "patrones",
        "warmup": "Calentamiento",
        "warmup_judgment": "2-3 series de aproximación progresivas hasta el peso de trabajo",
        "rest": "descanso",
        "sets": "series",
        "technique": "Técnica",
        "equipment": "Material",
        "muscles": "Músculos",
        "fallbacks": "Planes B",
        "low_readiness": "Baja frescura",
        "short_on_time": "Poco tiempo",
        "missing_equipment": "Material no disponible",
        "test_milestones": "Hitos de test",
        "checkin": "Check-in cada {days} días",
        "reason": "Motivo",
        "unscheduled": "sin programar",
        "volume_intensity": "Volumen x{volume}, intensidad x{intensity}",
        "set_targets": "Series semanales objetivo",
        "media_credit": "Medios e instrucciones de los ejercicios",
    },
}

_DAYS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "fr": ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"),
    "es": ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"),
}

_CSS = """
:root { --bg: #f6f7f9; --card: #ffffff; --ink: #1c2330; --muted: #5b6472;
  --line: #e3e6eb; --accent: #2563eb; --chip: #eef2f8; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #10141b; --card: #1a202b; --ink: #e8ecf2; --muted: #9aa4b2;
    --line: #2a3140; --accent: #7aa2ff; --chip: #232b39; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); line-height: 1.5;
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 1rem 1rem 4rem; }
header.top { padding: 1.5rem 0 0.5rem; }
header.top h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
header.top p { margin: 0.15rem 0; color: var(--muted); }
h2 { font-size: 1.15rem; margin: 2rem 0 0.5rem; }
details.week { background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; margin: 0.75rem 0; overflow: hidden; }
details.week > summary { cursor: pointer; padding: 0.85rem 1rem; font-weight: 600;
  list-style: none; display: flex; justify-content: space-between; gap: 0.5rem; }
details.week > summary::-webkit-details-marker { display: none; }
details.week > summary::after { content: "▾"; color: var(--muted); }
details.week[open] > summary::after { content: "▴"; }
.week-meta { padding: 0 1rem 0.5rem; color: var(--muted); font-size: 0.9rem; }
article.session { border-top: 1px solid var(--line); padding: 1rem; }
article.session h3 { margin: 0; font-size: 1.05rem; }
.purpose { color: var(--muted); margin: 0.25rem 0 0.75rem; font-size: 0.95rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; }
.chip { background: var(--chip); border-radius: 999px; padding: 0.15rem 0.65rem;
  font-size: 0.85rem; white-space: nowrap; }
.chip.strong { background: var(--accent); color: #fff; font-weight: 600; }
.block { display: flex; gap: 0.85rem; padding: 0.85rem 0; border-top: 1px dashed var(--line); }
.block .media { width: 96px; height: 96px; border-radius: 10px; flex-shrink: 0;
  background-color: var(--chip); background-size: cover; background-position: center; }
.block h4 { margin: 0 0 0.3rem; font-size: 1rem; }
.block .prio { color: var(--muted); font-weight: 400; font-size: 0.8rem; }
.grow { min-width: 0; flex: 1; }
.rule { margin: 0.35rem 0 0; font-size: 0.9rem; }
.notes, .warmup { margin: 0.35rem 0 0; font-size: 0.9rem; color: var(--muted); }
details.tech { margin-top: 0.5rem; font-size: 0.9rem; }
details.tech summary { cursor: pointer; color: var(--accent); }
details.tech ol { margin: 0.5rem 0 0.25rem 1.1rem; padding: 0; }
details.tech li { margin: 0.25rem 0; }
.tech-meta { color: var(--muted); }
details.fb { margin-top: 0.75rem; font-size: 0.9rem; }
details.fb summary { cursor: pointer; color: var(--muted); }
details.fb dl { margin: 0.5rem 0 0; }
details.fb dt { font-weight: 600; }
details.fb dd { margin: 0 0 0.4rem; color: var(--muted); }
ul.milestones { padding-left: 1.2rem; }
footer.credit { margin-top: 2.5rem; color: var(--muted); font-size: 0.8rem; }
@media print { details.week, details.tech, details.fb { open: true; }
  body { background: #fff; } }
"""


def _t(locale: str, key: str) -> str:
    return _LABELS.get(locale, _LABELS["en"])[key]


def _css_key(dataset_id: str) -> str:
    """Turn a dataset id into a token safe for a CSS class name."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", dataset_id)


class _MediaCatalog:
    """Resolves blocks against the dataset and embeds each GIF only once."""

    def __init__(self, index: ExerciseMediaIndex | None) -> None:
        self._index = index
        self.uris: dict[str, str] = {}

    def resolve(self, block: ExerciseBlock) -> tuple[DatasetExercise | None, str | None]:
        """Return the dataset record and the CSS class key of its embedded GIF."""
        if self._index is None:
            return None, None
        record = self._index.resolve(block.exercise, block.exercise_id)
        if record is None:
            return None, None
        key = _css_key(record.dataset_id)
        if key not in self.uris:
            uri = record.gif_data_uri()
            if uri is not None:
                self.uris[key] = uri
        return record, key if key in self.uris else None


def _chips(block: ExerciseBlock, locale: str) -> str:
    chips = [f'<span class="chip strong">{html.escape(volume_label(block))}</span>']
    intensity = intensity_label(block)
    if intensity:
        chips.append(f'<span class="chip">{html.escape(intensity)}</span>')
    if block.rest_s is not None:
        chips.append(f'<span class="chip">{_t(locale, "rest")} {block.rest_s}s</span>')
    return f'<div class="chips">{"".join(chips)}</div>'


def _warmup_html(session: SessionPlan, block: ExerciseBlock, locale: str) -> str:
    if "strength_heavy" not in session.qualities:
        return ""
    if block.warmup != "auto" or block.priority != "primary":
        return ""
    if block.load_kg is None:
        detail = _t(locale, "warmup_judgment")
    else:
        ramp = warmup_scheme(block.load_kg)
        if not ramp:
            return ""
        detail = ", ".join(
            f"{fraction * 100:.0f}% (~{num_label(block.load_kg * fraction)} kg) x{reps}"
            for fraction, reps in ramp
        )
    return f'<p class="warmup">{_t(locale, "warmup")} : {html.escape(detail)}</p>'


def _technique_html(record: DatasetExercise | None, locale: str) -> str:
    if record is None:
        return ""
    steps = record.steps(locale)
    if not steps:
        return ""
    items = "".join(f"<li>{html.escape(step)}</li>" for step in steps)
    muscles = ", ".join((record.target, *record.secondary_muscles))
    meta = (
        f'<p class="tech-meta">{_t(locale, "muscles")} : {html.escape(muscles)} · '
        f"{_t(locale, 'equipment')} : {html.escape(record.equipment)}</p>"
    )
    return (
        f'<details class="tech"><summary>{_t(locale, "technique")}</summary>'
        f"<ol>{items}</ol>{meta}</details>"
    )


def _block_html(
    session: SessionPlan, block: ExerciseBlock, catalog: _MediaCatalog, locale: str
) -> str:
    record, media_key = catalog.resolve(block)
    img = f'<div class="media m-{media_key}"></div>' if media_key else ""
    name = html.escape(block.exercise)
    parts = [
        f'<div class="block">{img}<div class="grow">',
        f'<h4>{name} <span class="prio">[{block.priority}]</span></h4>',
        _chips(block, locale),
        _warmup_html(session, block, locale),
        f'<p class="rule">{html.escape(block.progression_rule)}</p>',
    ]
    if block.notes:
        parts.append(f'<p class="notes">{html.escape(block.notes)}</p>')
    parts.append(_technique_html(record, locale))
    parts.append("</div></div>")
    return "".join(part for part in parts if part)


def _fallbacks_html(session: SessionPlan, locale: str) -> str:
    fallbacks = session.fallbacks
    rows = "".join(
        f"<dt>{_t(locale, key)}</dt><dd>{html.escape(value)}</dd>"
        for key, value in (
            ("low_readiness", fallbacks.low_readiness),
            ("short_on_time", fallbacks.short_on_time),
            ("missing_equipment", fallbacks.missing_equipment),
        )
    )
    return (
        f'<details class="fb"><summary>{_t(locale, "fallbacks")}</summary><dl>{rows}</dl></details>'
    )


def _session_html(session: SessionPlan, catalog: _MediaCatalog, locale: str) -> str:
    days = _DAYS.get(locale, _DAYS["en"])
    day = days[session.weekday] if session.weekday is not None else _t(locale, "unscheduled")
    qualities = ", ".join(session.qualities)
    if session.patterns:
        qualities += f" · {_t(locale, 'patterns')} : {', '.join(session.patterns)}"
    blocks = "".join(_block_html(session, block, catalog, locale) for block in session.blocks)
    return (
        f'<article class="session"><h3>{html.escape(session.id)} — {day} · '
        f"{session.est_minutes} min</h3>"
        f'<p class="purpose">{html.escape(session.purpose)} · {html.escape(qualities)}</p>'
        f"{blocks}{_fallbacks_html(session, locale)}</article>"
    )


def _week_html(week: WeekPlan, catalog: _MediaCatalog, locale: str, is_first: bool) -> str:
    flags = [
        _t(locale, flag)
        for flag, on in (("deload", week.is_deload), ("taper", week.is_taper))
        if on
    ]
    suffix = f" ({', '.join(flags)})" if flags else ""
    meta_lines = [
        _t(locale, "volume_intensity").format(
            volume=num_label(week.volume_factor), intensity=num_label(week.intensity_factor)
        )
    ]
    if week.notes:
        meta_lines.append(html.escape(week.notes))
    if week.weekly_set_targets:
        targets = ", ".join(f"{k}: {v}" for k, v in sorted(week.weekly_set_targets.items()))
        meta_lines.append(f"{_t(locale, 'set_targets')} : {targets}")
    sessions = "".join(_session_html(session, catalog, locale) for session in week.sessions)
    return (
        f'<details class="week"{" open" if is_first else ""}>'
        f"<summary>{_t(locale, 'week')} {week.week_index}{suffix}</summary>"
        f'<div class="week-meta">{"<br>".join(meta_lines)}</div>{sessions}</details>'
    )


def _header_html(plan: ProgramPlan, locale: str) -> str:
    title = f"{_t(locale, 'program')} v{plan.version} — {html.escape(plan.goal_id)}"
    lines = [f"<h1>{title}</h1>"]
    meta = [
        str(plan.created_on),
        _t(locale, "checkin").format(days=plan.checkin_cadence_days),
    ]
    if plan.reason:
        meta.append(f"{_t(locale, 'reason')} : {html.escape(plan.reason)}")
    lines.extend(f"<p>{item}</p>" for item in meta)
    if plan.test_milestones:
        rows = "".join(
            f"<li>{_t(locale, 'week')} {m.week_index} : {html.escape(m.protocol)} — "
            f"{html.escape(', '.join(m.targets))}</li>"
            for m in plan.test_milestones
        )
        lines.append(f"<h2>{_t(locale, 'test_milestones')}</h2><ul class='milestones'>{rows}</ul>")
    return f'<header class="top">{"".join(lines)}</header>'


def _media_css(catalog: _MediaCatalog) -> str:
    """One background-image rule per GIF: dedup without any JavaScript."""
    return "".join(
        f'.m-{key}{{background-image:url("{uri}")}}' for key, uri in catalog.uris.items()
    )


def render_program_html(
    plan: ProgramPlan, locale: str = "en", index: ExerciseMediaIndex | None = None
) -> str:
    """Render a ProgramPlan to a standalone, offline-ready HTML page.

    locale drives labels and exercise instructions (en/fr/es); index provides
    the media and is optional — without it the page still carries the full
    prescription, just without GIFs and technique steps.
    """
    catalog = _MediaCatalog(index)
    sections = []
    first = True
    for meso in plan.mesocycles:
        weeks = []
        for week in meso.weeks:
            weeks.append(_week_html(week, catalog, locale, first))
            first = False
        sections.append(
            f"<section><h2>Mesocycle {meso.index} — {meso.phase}</h2>{''.join(weeks)}</section>"
        )
    credit = ""
    if catalog.uris:
        credit = (
            f'<footer class="credit">{_t(locale, "media_credit")} : '
            '© <a href="https://gymvisual.com/">Gym visual</a> — '
            '<a href="https://github.com/hasaneyldrm/exercises-dataset">exercises-dataset'
            "</a> (MIT + media terms)</footer>"
        )
    title = f"{_t(locale, 'program')} v{plan.version} — {html.escape(plan.goal_id)}"
    return (
        f'<!doctype html><html lang="{locale}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_CSS}{_media_css(catalog)}</style></head><body><main>"
        f"{_header_html(plan, locale)}{''.join(sections)}{credit}</main>"
        "</body></html>"
    )
