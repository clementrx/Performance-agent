"""Deterministic protocol markdown rendering and citation ordering."""

from datetime import date

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import (
    AttemptPlan,
    CompetitionProtocol,
    DocumentedPractice,
    FuelingPlan,
    Guidance,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.programs.render_protocol import (
    protocol_citation_ids,
    render_protocol,
)

CITATIONS = {
    "carb-2017": ResolvedCitation(
        citation="Burke et al. (2017). Carbohydrates for training and competition. "
        "DOI: 10.1080/02640414.2011.585473.",
        stars="★★★★★",
        doi="10.1080/02640414.2011.585473",
        pmid=None,
    )
}


def _full_protocol():
    return CompetitionProtocol(
        version=1,
        event_id="nationals",
        event_date=date(2026, 8, 1),
        goal_id="sub-40-10k",
        created_on=date(2026, 7, 25),
        window_days=7,
        advice=[Guidance(text="Nothing new on race day.", cite="carb-2017")],
        days=[
            ProtocolDay(
                day_offset=-1,
                title="Carb load",
                lines=[ProtocolLine(text="8-12 g/kg carbs.", cite="carb-2017")],
            ),
            ProtocolDay(
                day_offset=0,
                title="Race day",
                lines=[ProtocolLine(text="Breakfast 3 h before.", time_hint="06:00")],
            ),
        ],
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        attempts=[
            AttemptPlan(
                lift="Squat",
                e1rm_kg=200,
                opener_kg=182.5,
                second_kg=192.5,
                third_kg=205,
                basis="engine",
            )
        ],
        fueling=FuelingPlan(carb_g_per_kg_low=8, carb_g_per_kg_high=12, window_hours=48),
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Documented in physique prep; small effect sizes.",
                warning="Dehydration risk; supervision required.",
            )
        ],
        checklist=["Pin race bib"],
    )


def test_citation_ids_ordered_and_deduped():
    assert protocol_citation_ids(_full_protocol()) == ["carb-2017"]


def test_markdown_renders_all_sections():
    text = render_protocol(_full_protocol(), citations=CITATIONS)
    assert "# Competition protocol v1 — nationals — 2026-08-01" in text
    assert "## J-1 — Carb load" in text
    assert "## J0 — Race day" in text
    assert "[06:00]" in text
    assert "## Pacing" in text
    assert "## Attempts" in text
    assert "182.5 / 192.5 / 205" in text
    assert "## Fueling" in text
    assert "## Documented practices" in text
    assert "⚠ Dehydration risk" in text
    assert "## Checklist" in text
    assert "## Sources" in text
    assert "★★★★★" in text


def test_cumulative_time_over_an_hour_renders_as_hms():
    protocol = _full_protocol()
    protocol.pacing.append(
        PacingSegment(
            label="Marathon finish",
            distance_m=42195,
            target_pace_s_per_km=250,
            cumulative_time_s=10500,
        )
    )
    text = render_protocol(protocol)
    assert "2:55:00" in text


def test_markdown_without_optional_sections_is_lean():
    protocol = CompetitionProtocol(
        version=1,
        event_id="local-5k",
        event_date=date(2026, 8, 1),
        goal_id="sub-20-5k",
        created_on=date(2026, 7, 28),
        window_days=3,
        days=[
            ProtocolDay(day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up 15 min.")])
        ],
    )
    text = render_protocol(protocol)
    assert "## Pacing" not in text
    assert "## Attempts" not in text
    assert "## Sources" not in text
