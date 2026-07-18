"""Deterministic CompetitionProtocol -> standalone phone page for the event.

Same rules as the session HTML: fully self-contained (inline CSS, zero
JavaScript, no external requests except DOI links), phone-first, en/fr/es
labels from the athlete's locale. J0 renders open, earlier days collapsed.
Practice warnings are visually flagged — the page never softens them.
"""

import html
from collections.abc import Mapping

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import CompetitionProtocol, ProtocolDay
from performance_agent.programs.render import clock_label, pace_label
from performance_agent.programs.render_protocol import protocol_citation_ids

_LABELS = {
    "en": {
        "protocol": "Competition protocol",
        "window": "Window",
        "goal": "Goal",
        "event_day": "Event day",
        "day": "Day",
        "advice": "Advice",
        "pacing": "Pacing",
        "segment": "Segment",
        "pace": "Pace",
        "cumulative": "Cumulative",
        "attempts": "Attempts",
        "fueling": "Fueling",
        "in_race": "In race",
        "practices": "Documented practices",
        "checklist": "Checklist",
        "sources": "Sources",
    },
    "fr": {
        "protocol": "Protocole de compétition",
        "window": "Fenêtre",
        "goal": "Objectif",
        "event_day": "Jour J",
        "day": "Jour",
        "advice": "Conseils",
        "pacing": "Allures",
        "segment": "Segment",
        "pace": "Allure",
        "cumulative": "Cumulé",
        "attempts": "Tentatives",
        "fueling": "Ravitaillement",
        "in_race": "En course",
        "practices": "Pratiques documentées",
        "checklist": "Checklist",
        "sources": "Sources",
    },
    "es": {
        "protocol": "Protocolo de competición",
        "window": "Ventana",
        "goal": "Objetivo",
        "event_day": "Día D",
        "day": "Día",
        "advice": "Consejos",
        "pacing": "Ritmos",
        "segment": "Segmento",
        "pace": "Ritmo",
        "cumulative": "Acumulado",
        "attempts": "Intentos",
        "fueling": "Avituallamiento",
        "in_race": "En carrera",
        "practices": "Prácticas documentadas",
        "checklist": "Checklist",
        "sources": "Fuentes",
    },
}

_CSS = """
:root { --bg: #f6f7f9; --card: #ffffff; --ink: #1c2330; --muted: #5b6472;
  --line: #e3e6eb; --accent: #2563eb; --chip: #eef2f8; --warn: #b45309;
  --warnbg: #fef3c7; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #10141b; --card: #1a202b; --ink: #e8ecf2; --muted: #9aa4b2;
    --line: #2a3140; --accent: #7aa2ff; --chip: #232b39; --warn: #fbbf24;
    --warnbg: #3a2f14; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); line-height: 1.5;
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 1rem 1rem 4rem; }
header.top h1 { margin: 1.5rem 0 0.25rem; font-size: 1.4rem; }
header.top p { margin: 0.15rem 0; color: var(--muted); }
h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; }
details.day { background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; margin: 0.6rem 0; overflow: hidden; }
details.day > summary { cursor: pointer; padding: 0.8rem 1rem; font-weight: 600;
  list-style: none; }
details.day > summary::-webkit-details-marker { display: none; }
details.day ul { margin: 0 0 0.8rem; padding: 0 1rem 0 2rem; }
details.day li { margin: 0.35rem 0; }
.hint { display: inline-block; background: var(--chip); border-radius: 999px;
  padding: 0 0.5rem; font-size: 0.85rem; margin-right: 0.3rem; }
li.warn { background: var(--warnbg); border-radius: 8px; padding: 0.25rem 0.5rem;
  list-style: none; margin-left: -1rem; }
.warnmark { color: var(--warn); font-weight: 700; }
sup.cite { color: var(--accent); font-weight: 600; }
table { border-collapse: collapse; width: 100%; background: var(--card);
  border-radius: 12px; overflow: hidden; }
th, td { border-bottom: 1px solid var(--line); padding: 0.45rem 0.7rem;
  text-align: left; font-size: 0.95rem; }
.practice { background: var(--warnbg); border-radius: 12px; padding: 0.7rem 1rem;
  margin: 0.6rem 0; }
.practice p { margin: 0.25rem 0; }
.practice .warnline { color: var(--warn); font-weight: 600; }
ul.checklist { padding-left: 1.2rem; }
section.sources ol { padding-left: 1.2rem; }
section.sources li { margin: 0.35rem 0; font-size: 0.9rem; }
section.sources .stars { color: var(--accent); letter-spacing: 0.05em; }
"""


def _t(locale: str, key: str) -> str:
    return _LABELS.get(locale, _LABELS["en"])[key]


def _marker(numbers: dict[str, int], cite: str | None) -> str:
    if cite is None or cite not in numbers:
        return ""
    return f'<sup class="cite">[{numbers[cite]}]</sup>'


def _day_html(day: ProtocolDay, numbers: dict[str, int], locale: str) -> str:
    title = (
        _t(locale, "event_day") if day.day_offset == 0 else f"{_t(locale, 'day')} J{day.day_offset}"
    )
    items = []
    for line in day.lines:
        hint = f'<span class="hint">{html.escape(line.time_hint)}</span>' if line.time_hint else ""
        warn = '<span class="warnmark">⚠ </span>' if line.warning else ""
        css = ' class="warn"' if line.warning else ""
        items.append(
            f"<li{css}>{hint}{warn}{html.escape(line.text)}{_marker(numbers, line.cite)}</li>"
        )
    is_open = " open" if day.day_offset == 0 else ""
    return (
        f'<details class="day"{is_open}><summary>{title} — {html.escape(day.title)}</summary>'
        f"<ul>{''.join(items)}</ul></details>"
    )


def _pacing_html(protocol: CompetitionProtocol, locale: str) -> str:
    if not protocol.pacing:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(seg.label)}</td><td>{seg.distance_m:g} m</td>"
        f"<td>{pace_label(seg.target_pace_s_per_km)}</td>"
        f"<td>{clock_label(seg.cumulative_time_s)}</td></tr>"
        for seg in protocol.pacing
    )
    return (
        f"<h2>🏁 {_t(locale, 'pacing')}</h2><table><tr><th>{_t(locale, 'segment')}</th>"
        f"<th></th><th>{_t(locale, 'pace')}</th><th>{_t(locale, 'cumulative')}</th></tr>"
        f"{rows}</table>"
    )


def _attempts_html(protocol: CompetitionProtocol, locale: str) -> str:
    if not protocol.attempts:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(a.lift)}</td><td>{a.opener_kg:g}</td>"
        f"<td>{a.second_kg:g}</td><td>{a.third_kg:g}</td></tr>"
        for a in protocol.attempts
    )
    return (
        f"<h2>🏋️ {_t(locale, 'attempts')}</h2><table><tr><th></th><th>1</th><th>2</th>"
        f"<th>3</th></tr>{rows}</table>"
    )


def _fueling_html(protocol: CompetitionProtocol, numbers: dict[str, int], locale: str) -> str:
    fueling = protocol.fueling
    if fueling is None:
        return ""
    lines = [
        f"<li>{fueling.carb_g_per_kg_low:g}-{fueling.carb_g_per_kg_high:g} g/kg/day — "
        f"{fueling.window_hours} h{_marker(numbers, fueling.cite)}</li>"
    ]
    if fueling.race_carb_g_per_h_low is not None and fueling.race_carb_g_per_h_high is not None:
        lines.append(
            f"<li>{_t(locale, 'in_race')}: {fueling.race_carb_g_per_h_low:g}-"
            f"{fueling.race_carb_g_per_h_high:g} g/h</li>"
        )
    return f"<h2>🍝 {_t(locale, 'fueling')}</h2><ul>{''.join(lines)}</ul>"


def _practices_html(protocol: CompetitionProtocol, numbers: dict[str, int], locale: str) -> str:
    if not protocol.practices:
        return ""
    cards = "".join(
        f'<div class="practice"><p><strong>{html.escape(p.name)}</strong> — '
        f"{html.escape(p.summary)}{_marker(numbers, p.cite)}</p>"
        f'<p class="warnline">⚠ {html.escape(p.warning)}</p></div>'
        for p in protocol.practices
    )
    return f"<h2>⚠️ {_t(locale, 'practices')}</h2>{cards}"


def _sources_html(
    citations: Mapping[str, ResolvedCitation], numbers: dict[str, int], locale: str
) -> str:
    ordered = sorted((cid for cid in numbers if cid in citations), key=lambda cid: numbers[cid])
    if not ordered:
        return ""
    rows = []
    for cid in ordered:
        resolved = citations[cid]
        link = (
            f' <a href="https://doi.org/{html.escape(resolved.doi)}">DOI</a>'
            if resolved.doi
            else ""
        )
        rows.append(
            f'<li><span class="stars">{resolved.stars}</span> '
            f"{html.escape(resolved.citation)}{link}</li>"
        )
    return (
        f'<section class="sources"><h2>📚 {_t(locale, "sources")}</h2>'
        f"<ol>{''.join(rows)}</ol></section>"
    )


def render_protocol_html(
    protocol: CompetitionProtocol,
    locale: str = "en",
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str:
    """Render the protocol to a standalone, offline-ready phone page."""
    ids = [cid for cid in protocol_citation_ids(protocol) if cid in citations] if citations else []
    numbers = {cid: i for i, cid in enumerate(ids, start=1)}
    advice = ""
    if protocol.advice:
        rows = "".join(
            f"<li>{html.escape(g.text)}{_marker(numbers, g.cite)}</li>" for g in protocol.advice
        )
        advice = f"<h2>💡 {_t(locale, 'advice')}</h2><ul>{rows}</ul>"
    days = "".join(_day_html(day, numbers, locale) for day in protocol.days)
    checklist = ""
    if protocol.checklist:
        items = "".join(f"<li>☐ {html.escape(item)}</li>" for item in protocol.checklist)
        checklist = f"<h2>🎒 {_t(locale, 'checklist')}</h2><ul class='checklist'>{items}</ul>"
    title = (
        f"{_t(locale, 'protocol')} v{protocol.version} — {html.escape(protocol.event_id)} — "
        f"{protocol.event_date.isoformat()}"
    )
    header = (
        f'<header class="top"><h1>{title}</h1>'
        f"<p>{_t(locale, 'window')}: J-{protocol.window_days} → J0 · "
        f"{_t(locale, 'goal')}: {html.escape(protocol.goal_id)}</p></header>"
    )
    return (
        f'<!doctype html><html lang="{locale}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_CSS}</style></head><body><main>"
        f"{header}{advice}{days}{_pacing_html(protocol, locale)}"
        f"{_attempts_html(protocol, locale)}{_fueling_html(protocol, numbers, locale)}"
        f"{_practices_html(protocol, numbers, locale)}{checklist}"
        f"{_sources_html(citations or {}, numbers, locale)}</main></body></html>"
    )
