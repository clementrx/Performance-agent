"""Build the Typst source for a report (pure string assembly, fully escaped)."""

from dataclasses import dataclass
from typing import Literal

from performance_agent.reports.labels import LABELS
from performance_agent.reports.sections import (
    BanisterRow,
    LoadTrends,
    QualityRateRow,
    RateRow,
    ResponseSummary,
    SeasonOverview,
    ToleranceRow,
)
from performance_agent.reports.typst_text import escape_typst, markdown_to_typst

ReportMode = Literal["coach", "expert"]

_TOLERANCE_LABEL_KEYS = {
    "higher_volume_higher_fatigue": "tol_higher_fatigue",
    "higher_volume_lower_fatigue": "tol_lower_fatigue",
    "no_clear_direction": "tol_no_direction",
}


@dataclass(frozen=True)
class ReportContext:
    """Everything the report needs, already fetched and validated by the caller."""

    locale: str
    mode: ReportMode
    athlete_name: str
    goal_statement: str
    version: int
    created_on: str
    reason: str | None
    body_markdown: str
    citations: list[str]
    season: SeasonOverview | None = None
    load: LoadTrends | None = None
    response: ResponseSummary | None = None


def _kv(label: str, value: str) -> str:
    """A '*Label:* value' line with an explicit Typst line break."""
    return f"*{escape_typst(label)}:* {escape_typst(value)} \\"


def _num(value: float | None, labels: dict[str, str]) -> str:
    return f"{value:.2f}" if value is not None else labels["not_available"]


def _weeks_str(weeks: list[int], labels: dict[str, str]) -> str:
    return f"{labels['week']} " + ", ".join(str(week) for week in weeks)


def _rate_str(rate: RateRow, labels: dict[str, str]) -> str:
    return (
        f"{rate.pct_per_week * 100:+.1f}%/{labels['per_week']} "
        f"(n={rate.n}, {rate.window_weeks:.0f} {labels['per_week']}, r2={rate.r2:.2f})"
    )


def _season_lines(season: SeasonOverview, labels: dict[str, str], mode: ReportMode) -> list[str]:
    """Season overview: terse in coach mode (events + taper), full in expert mode."""
    lines = [f"= {escape_typst(labels['season_title'])}", ""]
    if mode == "expert" and season.season_ref:
        lines.append(_kv(labels["season_ref"], season.season_ref))
    if season.events:
        lines.append(f"*{escape_typst(labels['season_events'])}:*")
        lines += [
            f"- {escape_typst(event.date)} ({escape_typst(event.priority)}) "
            f"{escape_typst(event.label)}"
            for event in season.events
        ]
    if mode == "expert" and season.phases:
        lines.append(f"*{escape_typst(labels['season_phases'])}:*")
        lines += [
            f"- {escape_typst(labels['week'])} {phase.start_week}-{phase.end_week}: "
            f"{escape_typst(phase.phase)}"
            for phase in season.phases
        ]
    if season.taper_weeks:
        lines.append(_kv(labels["season_taper"], _weeks_str(season.taper_weeks, labels)))
    if mode == "expert" and season.test_weeks:
        lines.append(_kv(labels["season_tests"], _weeks_str(season.test_weeks, labels)))
    lines.append("")
    return lines


def _load_summary_line(load: LoadTrends, labels: dict[str, str]) -> str:
    text = (
        f"{labels['load_summary']}: {load.last_week_total:.0f} "
        f"({load.external_share * 100:.0f}% {labels['load_external']}); TSB {load.tsb:+.0f}"
    )
    return escape_typst(text)


def _load_lines(load: LoadTrends, labels: dict[str, str], mode: ReportMode) -> list[str]:
    """Load trends: a one-line summary in coach mode, the full table in expert mode."""
    if mode == "coach":
        return [_load_summary_line(load, labels), ""]
    last_week = (
        f"{load.last_week_total:.0f} ({load.external_share * 100:.0f}% {labels['load_external']})"
    )
    fitness = f"CTL {load.ctl:.0f} / ATL {load.atl:.0f} / TSB {load.tsb:+.0f}"
    return [
        f"= {escape_typst(labels['load_title'])}",
        "",
        _kv(labels["load_last_week"], last_week),
        _kv(labels["load_monotony"], _num(load.monotony, labels)),
        _kv(labels["load_strain"], _num(load.strain, labels)),
        _kv(labels["load_fitness"], fitness),
        "",
    ]


def _tolerance_line(flag: ToleranceRow, labels: dict[str, str]) -> str:
    direction = labels[_TOLERANCE_LABEL_KEYS[flag.direction]]
    return f"- {escape_typst(direction)} (r={flag.correlation:+.2f}, n={flag.n_weeks})"


def _quality_rate_line(rate: QualityRateRow, labels: dict[str, str]) -> str:
    row = RateRow(rate.quality, rate.pct_per_week, rate.n, rate.window_weeks, rate.r2)
    head = f"{escape_typst(rate.quality)} ({escape_typst(rate.kpi_id)})"
    return f"- {head}: {escape_typst(_rate_str(row, labels))}"


def _banister_lines(fit: BanisterRow, labels: dict[str, str]) -> list[str]:
    """The fitted Banister summary: basis (usable), params, and uncertainty."""
    lines = [f"*{escape_typst(labels['response_banister'])}:*"]
    if not fit.usable:
        lines.append(f"- {escape_typst(labels['response_fit_unusable'])}")
        return lines
    params = (
        f"tau1={fit.tau1:.0f}d / tau2={fit.tau2:.0f}d, "
        f"k1={fit.k1:.3f} (+/-{fit.k1_ci_half:.3f}), k2={fit.k2:.3f} (+/-{fit.k2_ci_half:.3f})"
    )
    quality = (
        f"r2={fit.r2:.2f}, n={fit.n_performance_points} {labels['response_fit_points']}, "
        f"{fit.n_load_days} {labels['response_fit_load_days']}"
    )
    lines.append(f"- {escape_typst(params)}")
    lines.append(f"- {escape_typst(quality)} ({escape_typst(labels['response_fit_ci_note'])})")
    return lines


def _response_lines(response: ResponseSummary, labels: dict[str, str]) -> list[str]:
    """Response summary (expert only): measured-vs-prior rate, adherence, caveats."""
    lines = [f"= {escape_typst(labels['response_title'])}", ""]
    if response.goal_rate is not None:
        lines.append(_kv(labels["response_rate"], _rate_str(response.goal_rate, labels)))
    else:
        lines.append(_kv(labels["response_rate"], labels["response_prior"]))
    lines += [
        f"- {escape_typst(rate.label)}: {escape_typst(_rate_str(rate, labels))}"
        for rate in response.lift_rates
    ]
    if response.adherence:
        lines.append(f"*{escape_typst(labels['response_adherence'])}:*")
        lines += [
            f"- {escape_typst(item.quality)}: {item.adherence_pct:.0f}% "
            f"({item.done}/{item.partial}/{item.modified}/{item.missed})"
            for item in response.adherence
        ]
    if response.tolerance:
        lines.append(f"*{escape_typst(labels['response_tolerance'])}:*")
        lines += [_tolerance_line(flag, labels) for flag in response.tolerance]
    if response.quality_rates:
        lines.append(f"*{escape_typst(labels['response_quality_rates'])}:*")
        lines += [_quality_rate_line(rate, labels) for rate in response.quality_rates]
    if response.banister is not None:
        lines += _banister_lines(response.banister, labels)
    if response.caveats:
        lines.append(f"*{escape_typst(labels['response_caveats'])}:*")
        lines += [f"- {escape_typst(caveat)}" for caveat in response.caveats]
    lines.append("")
    return lines


def _header_lines(context: ReportContext, labels: dict[str, str]) -> list[str]:
    parts = [
        f'#set text(lang: "{context.locale}")',
        "#set page(margin: 2cm)",
        f"= {escape_typst(labels['report_title'])}",
        "",
        f"*{escape_typst(labels['athlete'])}:* {escape_typst(context.athlete_name)} \\",
        f"*{escape_typst(labels['goal'])}:* {escape_typst(context.goal_statement)} \\",
        f"*{escape_typst(labels['program_version'])}:* v{context.version} \\",
        f"*{escape_typst(labels['generated_on'])}:* {escape_typst(context.created_on)}",
        "",
    ]
    if context.mode == "expert" and context.reason:
        parts += [
            f"*{escape_typst(labels['adaptation_reason'])}:* {escape_typst(context.reason)}",
            "",
        ]
    return parts


def build_report_source(context: ReportContext) -> str:
    """Assemble the full Typst document source."""
    labels = LABELS.get(context.locale)
    if labels is None:
        msg = f"unsupported report locale {context.locale!r}; valid locales: {sorted(LABELS)}"
        raise ValueError(msg)
    parts = _header_lines(context, labels)
    parts += ["#line(length: 100%)", "", markdown_to_typst(context.body_markdown), ""]
    if context.season is not None:
        parts += _season_lines(context.season, labels, context.mode)
    if context.load is not None:
        parts += _load_lines(context.load, labels, context.mode)
    if context.response is not None and context.mode == "expert":
        parts += _response_lines(context.response, labels)
    if context.mode == "expert" and context.citations:
        parts += [f"= {escape_typst(labels['references'])}", ""]
        parts += [f"- {escape_typst(citation)}" for citation in context.citations]
        parts += ["", escape_typst(labels["evidence_note"])]
    return "\n".join(parts)
