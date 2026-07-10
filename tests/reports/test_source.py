from dataclasses import replace

import pytest

from performance_agent.reports.source import ReportContext, build_report_source

CONTEXT = ReportContext(
    locale="fr",
    mode="expert",
    athlete_name="Clément",
    goal_statement="10 km sous 45:00",
    version=2,
    created_on="2026-07-10",
    reason="plateau à la semaine 4",
    body_markdown="# Semaine 1\n- footing 45 min **facile**",
    citations=["Doe J (2020). Strength and economy. J Sports Sci. DOI: 10.1000/x."],
)


def test_source_carries_locale_and_metadata():
    source = build_report_source(CONTEXT)
    assert '#set text(lang: "fr")' in source
    assert "Clément" in source
    assert "10 km sous 45:00" in source
    assert "2026-07-10" in source
    assert "v2" in source


def test_body_is_converted_and_escaped():
    source = build_report_source(CONTEXT)
    assert "= Semaine 1" in source
    assert "*facile*" in source


def test_expert_mode_includes_references_and_reason():
    source = build_report_source(CONTEXT)
    assert "Doe J (2020)" in source
    assert "plateau à la semaine 4" in source


def test_coach_mode_omits_references_and_reason():
    coach = replace(CONTEXT, mode="coach")
    source = build_report_source(coach)
    assert "Doe J (2020)" not in source
    assert "plateau à la semaine 4" not in source


def test_athlete_text_cannot_inject_typst():
    hostile = replace(CONTEXT, athlete_name='#eval("boom")', citations=[])
    source = build_report_source(hostile)
    # "#eval(...)" not in source is impossible to also require alongside the
    # escaped form below: "\#eval" (backslash-prefix escaping) necessarily
    # contains "#eval" as a substring. The escaped form is the actual
    # security property (see tests/reports/test_typst_text.py precedent).
    assert "\\#eval" in source


def test_unknown_locale_is_a_readable_error():
    bogus = replace(CONTEXT, locale="de")
    with pytest.raises(ValueError, match="de"):
        build_report_source(bogus)


def test_french_labels_used():
    source = build_report_source(CONTEXT)
    assert "Rapport d'entraînement" in source
