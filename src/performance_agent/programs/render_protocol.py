"""Deterministic CompetitionProtocol -> markdown (the human/audit view).

Generated at save time from the structured protocol, like the program markdown,
so the document can never drift from the source of truth. Citation numbering
order (advice, then day lines, then fueling, then practices) is shared with the
HTML page via protocol_citation_ids.
"""

from collections.abc import Mapping

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import CompetitionProtocol, FuelingPlan, ProtocolLine
from performance_agent.programs.render import clock_label, num_label, pace_label


def protocol_citation_ids(protocol: CompetitionProtocol) -> list[str]:
    """Every corpus id the protocol cites, in first-appearance order, deduplicated."""
    ids: list[str] = []
    seen: set[str] = set()

    def add(cite: str | None) -> None:
        if cite and cite not in seen:
            seen.add(cite)
            ids.append(cite)

    for guidance in protocol.advice:
        add(guidance.cite)
    for day in protocol.days:
        for line in day.lines:
            add(line.cite)
    if protocol.fueling is not None:
        add(protocol.fueling.cite)
    for practice in protocol.practices:
        add(practice.cite)
    return ids


def _day_label(offset: int) -> str:
    return "J0" if offset == 0 else f"J{offset}"


def _line_text(line: ProtocolLine) -> str:
    parts = []
    if line.time_hint:
        parts.append(f"[{line.time_hint}]")
    parts.append(line.text)
    if line.warning:
        parts.append("⚠")
    if line.cite:
        parts.append(f"[{line.cite}]")
    return "- " + " ".join(parts)


def _advice_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = ["", "## Advice"]
    for guidance in protocol.advice:
        suffix = f" [{guidance.cite}]" if guidance.cite else ""
        lines.append(f"- {guidance.text}{suffix}")
    return lines


def _days_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = []
    for day in protocol.days:
        lines += ["", f"## {_day_label(day.day_offset)} — {day.title}"]
        for line in day.lines:
            lines.append(_line_text(line))
    return lines


def _pacing_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = [
        "",
        "## Pacing",
        "",
        "| Segment | Distance | Pace | Cumulative |",
        "|---|---|---|---|",
    ]
    for seg in protocol.pacing:
        lines.append(
            f"| {seg.label} | {num_label(seg.distance_m)} m "
            f"| {pace_label(seg.target_pace_s_per_km)} "
            f"| {clock_label(seg.cumulative_time_s)} |"
        )
    return lines


def _attempts_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = ["", "## Attempts"]
    for attempt in protocol.attempts:
        flags = f" ({', '.join(attempt.flags)})" if attempt.flags else ""
        lines.append(
            f"- {attempt.lift}: {num_label(attempt.opener_kg)} / {num_label(attempt.second_kg)} "
            f"/ {num_label(attempt.third_kg)} kg — e1RM {num_label(attempt.e1rm_kg)} kg, "
            f"{attempt.basis}{flags}"
        )
    return lines


def _fueling_lines(fueling: FuelingPlan) -> list[str]:
    lines: list[str] = ["", "## Fueling"]
    cite = f" [{fueling.cite}]" if fueling.cite else ""
    lines.append(
        f"- {num_label(fueling.carb_g_per_kg_low)}-{num_label(fueling.carb_g_per_kg_high)} "
        f"g/kg/day carbs over the final {fueling.window_hours} h{cite}"
    )
    has_race_range = (
        fueling.race_carb_g_per_h_low is not None and fueling.race_carb_g_per_h_high is not None
    )
    if has_race_range:
        lines.append(
            f"- In race: {num_label(fueling.race_carb_g_per_h_low)}-"
            f"{num_label(fueling.race_carb_g_per_h_high)} g/h"
        )
    return lines


def _practices_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = ["", "## Documented practices"]
    for practice in protocol.practices:
        cite = f" [{practice.cite}]" if practice.cite else ""
        lines.append(f"- **{practice.name}** — {practice.summary}{cite}")
        lines.append(f"  ⚠ {practice.warning}")
    return lines


def _checklist_lines(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = ["", "## Checklist"]
    lines += [f"- [ ] {item}" for item in protocol.checklist]
    return lines


def _sections(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = []
    if protocol.advice:
        lines += _advice_lines(protocol)
    lines += _days_lines(protocol)
    if protocol.pacing:
        lines += _pacing_lines(protocol)
    if protocol.attempts:
        lines += _attempts_lines(protocol)
    if protocol.fueling is not None:
        lines += _fueling_lines(protocol.fueling)
    if protocol.practices:
        lines += _practices_lines(protocol)
    if protocol.checklist:
        lines += _checklist_lines(protocol)
    return lines


def render_protocol(
    protocol: CompetitionProtocol,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str:
    """Render the protocol to markdown (deterministic; Sources iff citations)."""
    lines = [
        f"# Competition protocol v{protocol.version} — {protocol.event_id} — "
        f"{protocol.event_date.isoformat()}",
        "",
        f"- Window: J-{protocol.window_days} → J0",
        f"- Goal: {protocol.goal_id}",
    ]
    if protocol.reason:
        lines.append(f"- Reason: {protocol.reason}")
    lines += _sections(protocol)
    if citations is not None:
        ids = [cid for cid in protocol_citation_ids(protocol) if cid in citations]
        if ids:
            lines += ["", "## Sources"]
            for number, cid in enumerate(ids, start=1):
                resolved = citations[cid]
                lines.append(f"{number}. {resolved.stars} {resolved.citation}")
    return "\n".join(lines).strip() + "\n"
