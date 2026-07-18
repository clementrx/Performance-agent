"""Protocol phone page: offline, no JS, warnings flagged, starred sources."""

from datetime import date

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import (
    CompetitionProtocol,
    DocumentedPractice,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.programs.render_protocol_html import render_protocol_html

CITATIONS = {
    "carb-2017": ResolvedCitation(
        citation="Burke et al. (2017). Carbohydrates for training and competition. "
        "DOI: 10.1080/02640414.2011.585473.",
        stars="★★★★★",
        doi="10.1080/02640414.2011.585473",
        pmid=None,
    )
}


def _protocol():
    return CompetitionProtocol(
        version=1,
        event_id="nationals",
        event_date=date(2026, 8, 1),
        goal_id="sub-40-10k",
        created_on=date(2026, 7, 25),
        window_days=7,
        days=[
            ProtocolDay(
                day_offset=-1,
                title="Veille",
                lines=[ProtocolLine(text="8-12 g/kg carbs.", cite="carb-2017")],
            ),
            ProtocolDay(
                day_offset=0,
                title="Race day",
                lines=[
                    ProtocolLine(text="Breakfast.", time_hint="06:00"),
                    ProtocolLine(text="No new shoes.", warning=True),
                ],
            ),
        ],
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Documented in physique prep.",
                warning="Dehydration risk; supervision required.",
            )
        ],
        checklist=["Pin race bib"],
    )


def test_page_is_selfcontained_and_scriptless():
    page = render_protocol_html(_protocol(), citations=CITATIONS)
    assert page.startswith("<!doctype html>")
    assert "<script" not in page
    assert "http" not in page.replace("https://doi.org/", "")


def test_event_day_open_warnings_and_sources_rendered():
    page = render_protocol_html(_protocol(), citations=CITATIONS)
    assert '<details class="day" open>' in page
    assert "⚠" in page
    assert "Dehydration risk" in page
    assert "★★★★★" in page
    assert "https://doi.org/10.1080/02640414.2011.585473" in page
    assert "[1]" in page


def test_unresolved_citation_id_is_skipped_from_numbering():
    protocol = _protocol().model_copy(
        update={
            "days": [
                ProtocolDay(
                    day_offset=0,
                    title="Race day",
                    lines=[
                        ProtocolLine(text="Missing source.", cite="missing-id"),
                        ProtocolLine(text="Known source.", cite="carb-2017"),
                    ],
                )
            ]
        }
    )
    page = render_protocol_html(protocol, citations=CITATIONS)
    assert "Missing source.</li>" in page  # no <sup class="cite"> marker attached
    assert 'Known source.<sup class="cite">[1]</sup>' in page
    assert page.count('<li><span class="stars">') == 1


def test_line_text_is_escaped():
    protocol = _protocol().model_copy(
        update={
            "days": [
                ProtocolDay(
                    day_offset=0,
                    title="Race day",
                    lines=[ProtocolLine(text="<b>&bold</b>")],
                )
            ]
        }
    )
    page = render_protocol_html(protocol)
    assert "<b>&bold</b>" not in page
    assert "&lt;b&gt;&amp;bold&lt;/b&gt;" in page


def test_french_labels():
    page = render_protocol_html(_protocol(), locale="fr", citations=CITATIONS)
    assert "Jour J" in page
    assert "Allures" in page


def test_cumulative_time_over_one_hour_uses_hms():
    protocol = _protocol().model_copy(
        update={
            "pacing": [
                PacingSegment(
                    label="42 km",
                    distance_m=42195,
                    target_pace_s_per_km=249,
                    cumulative_time_s=10500,
                )
            ]
        }
    )
    page = render_protocol_html(protocol)
    assert "2:55:00" in page
