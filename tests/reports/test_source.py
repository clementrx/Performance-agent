from dataclasses import replace

import pytest

from performance_agent.reports.sections import (
    AdherenceRow,
    BanisterRow,
    LoadTrends,
    QualityRateRow,
    RateRow,
    ResponseSummary,
    SeasonEventRow,
    SeasonOverview,
    ToleranceRow,
)
from performance_agent.reports.source import ReportContext, build_report_source

SEASON = SeasonOverview(
    season_ref="two races 16 weeks apart",
    events=[SeasonEventRow(date="2026-10-03", priority="A", label="Championnat")],
    phases=[],
    taper_weeks=[6],
    test_weeks=[4],
)
LOAD = LoadTrends(
    last_week_total=1030.0,
    external_share=0.34,
    monotony=1.8,
    strain=1854.0,
    ctl=42.0,
    atl=55.0,
    tsb=-13.0,
    days_of_history=21,
)
RESPONSE = ResponseSummary(
    goal_rate=RateRow(label="10 km", pct_per_week=0.012, n=6, window_weeks=6.0, r2=0.7),
    lift_rates=[],
    quality_rates=[
        QualityRateRow(
            quality="aerobic_capacity",
            kpi_id="run-10k-time",
            pct_per_week=-0.01,
            n=6,
            window_weeks=6.0,
            r2=0.8,
        )
    ],
    adherence=[AdherenceRow("endurance_easy", 82.0, 9, 1, 0, 1)],
    tolerance=[ToleranceRow("higher_volume_higher_fatigue", 0.6, 5)],
    banister=BanisterRow(
        usable=True,
        tau1=40.0,
        tau2=8.0,
        k1=0.1,
        k2=0.14,
        r2=0.95,
        k1_ci_half=0.02,
        k2_ci_half=0.03,
        n_load_days=84,
        n_performance_points=6,
    ),
    caveats=["mesuré sur six séances provisoires"],
)

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
    season=SEASON,
    load=LOAD,
    response=RESPONSE,
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


def test_expert_mode_renders_all_three_sections():
    source = build_report_source(CONTEXT)
    assert "Vue de saison" in source
    assert "Championnat" in source
    assert "Tendances de charge" in source
    assert "Monotonie" in source
    assert "Synthèse de la réponse" in source
    assert "mesuré sur six séances provisoires" in source
    # Fitted-response summary: Banister params + per-quality rates + CI note.
    assert "Modèle fitness-fatigue ajusté" in source
    assert "tau1" in source and "40d" in source
    assert "IC 95% approximatifs" in source
    assert "Taux par qualité" in source


def test_unusable_banister_is_labelled_population():
    unusable = replace(
        RESPONSE,
        banister=BanisterRow(
            usable=False,
            tau1=1.0,
            tau2=1.0,
            k1=0.0,
            k2=0.0,
            r2=0.0,
            k1_ci_half=0.0,
            k2_ci_half=0.0,
            n_load_days=10,
            n_performance_points=2,
        ),
    )
    source = build_report_source(replace(CONTEXT, response=unusable))
    assert "modèle populationnel" in source
    assert "tau1" not in source


def test_coach_mode_is_terse():
    coach = replace(CONTEXT, mode="coach")
    source = build_report_source(coach)
    # season stays (events + taper) but the response summary is expert-only
    assert "Championnat" in source
    assert "Synthèse de la réponse" not in source
    # load collapses to a one-line summary, not the full table
    assert "Charge (dernière semaine)" in source
    assert "Tendances de charge" not in source


def test_sections_absent_when_data_missing():
    bare = replace(CONTEXT, season=None, load=None, response=None)
    source = build_report_source(bare)
    assert "Vue de saison" not in source
    assert "Tendances de charge" not in source
    assert "Synthèse de la réponse" not in source
