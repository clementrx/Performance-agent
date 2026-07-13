import shutil
import subprocess
from datetime import date, datetime

import pytest

from performance_agent.memory.schemas import (
    AdherenceQuality,
    CalendarEvent,
    Goal,
    MeasuredRate,
    Profile,
    ResponseProfile,
    SessionEntry,
)
from performance_agent.memory.store import (
    append_session,
    save_program,
    save_response_profile,
    upsert_calendar_event,
    upsert_goal,
    write_profile,
)
from performance_agent.reports.renderer import render_report_files
from tests.program_plans import minimal_plan

TODAY = date(2026, 7, 10)
HAS_TYPST = shutil.which("typst") is not None


def _seed_athlete(tmp_path, body: str) -> None:
    write_profile(tmp_path, Profile(locale="fr", display_name="Clément"))
    upsert_goal(tmp_path, Goal(id="sub-45-10k", statement="10 km sous 45:00"))
    # body is rendered into the program via a block note so the citation gate
    # sees whatever locator the test embeds.
    save_program(tmp_path, minimal_plan(goal_id="sub-45-10k", note=body), today=TODAY)


def test_fabricated_reference_aborts_before_any_file_is_written(tmp_path):
    _seed_athlete(tmp_path, "# Plan\nProuvé par la science (doi:10.9999/fake).")
    with pytest.raises(ValueError, match="10.9999/fake"):  # noqa: RUF043 - literal DOI
        render_report_files(tmp_path, mode="expert")
    assert not (tmp_path / "reports").exists()


def test_source_file_is_always_written(tmp_path, monkeypatch):
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    monkeypatch.setattr("performance_agent.reports.renderer._typst_binary", lambda: None)
    with pytest.raises(ValueError, match="typst"):
        render_report_files(tmp_path, mode="coach")
    source_path = tmp_path / "reports" / "program-v1-coach-fr.typ"
    assert source_path.exists()
    assert "= Rapport d'entraînement" in source_path.read_text(encoding="utf-8")


def test_compile_timeout_is_a_readable_error(tmp_path, monkeypatch):
    _seed_athlete(tmp_path, "# Plan\n- ok")

    def _boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["typst"], timeout=60)

    monkeypatch.setattr("performance_agent.reports.renderer.subprocess.run", _boom)
    with pytest.raises(ValueError, match="timed out"):
        render_report_files(tmp_path, mode="coach")


def test_missing_program_is_a_readable_error(tmp_path):
    write_profile(tmp_path, Profile(locale="en"))
    with pytest.raises(ValueError, match="save_program"):
        render_report_files(tmp_path, mode="coach")


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_pdf_compiles_end_to_end(tmp_path):
    _seed_athlete(tmp_path, "# Semaine 1\n- footing 45 min **facile**\n\nBon courage !")
    result = render_report_files(tmp_path, mode="coach")
    assert result.pdf_path.exists()
    assert result.pdf_path.name == "program-v1-coach-fr.pdf"
    assert result.pdf_path.stat().st_size > 1000
    assert result.source_path.exists()


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_expert_references_carry_stars(tmp_path):
    from performance_agent.evidence.corpus import load_corpus  # noqa: PLC0415

    entry = load_corpus()[0]
    locator = f"DOI: {entry.doi}" if entry.doi else f"PMID: {entry.pmid}"
    _seed_athlete(tmp_path, f"# Plan\nBloc force ({locator}).")
    result = render_report_files(tmp_path, mode="expert")
    text = result.source_path.read_text(encoding="utf-8")
    references_block = text.split("Références")[1]
    assert "★" in references_block
    # stars on the citation bullet itself, not just in the legend below it
    assert "- ★" in references_block


def _no_typst(monkeypatch):
    monkeypatch.setattr("performance_agent.reports.renderer._typst_binary", lambda: None)


def test_descriptive_sections_land_in_source(tmp_path, monkeypatch):
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nats", date=date(2026, 10, 3), kind="competition", priority="A", label="Championnat"
        ),
    )
    for day, rpe in ((1, 6), (3, 7), (5, 8)):
        append_session(
            tmp_path,
            SessionEntry(performed_at=datetime(2026, 7, day, 9, 0), rpe=rpe, duration_min=50),
        )
    _no_typst(monkeypatch)
    with pytest.raises(ValueError, match="typst"):
        render_report_files(tmp_path, mode="coach")
    source = (tmp_path / "reports" / "program-v1-coach-fr.typ").read_text(encoding="utf-8")
    assert "Vue de saison" in source
    assert "Championnat" in source
    assert "Charge (dernière semaine)" in source


def test_response_summary_lands_in_expert_source(tmp_path, monkeypatch):
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    save_response_profile(
        tmp_path,
        ResponseProfile(
            as_of=date(2026, 7, 12),
            goal_id="sub-45-10k",
            per_goal_measured_rate=MeasuredRate(value=0.012, n=6, window_weeks=6.0, r2=0.7),
            adherence_by_quality=[
                AdherenceQuality(
                    quality="endurance_easy",
                    done=9,
                    partial=1,
                    modified=0,
                    missed=1,
                    adherence_pct=82.0,
                )
            ],
            caveats=["mesuré sur six séances provisoires"],
        ),
    )
    _no_typst(monkeypatch)
    with pytest.raises(ValueError, match="typst"):
        render_report_files(tmp_path, mode="expert")
    source = (tmp_path / "reports" / "program-v1-expert-fr.typ").read_text(encoding="utf-8")
    assert "Synthèse de la réponse" in source
    assert "mesuré sur six séances provisoires" in source


def test_sections_skip_gracefully_when_no_extra_data(tmp_path, monkeypatch):
    # only a program is seeded; season data still comes from the plan's season_ref
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    _no_typst(monkeypatch)
    with pytest.raises(ValueError, match="typst"):
        render_report_files(tmp_path, mode="coach")
    source = (tmp_path / "reports" / "program-v1-coach-fr.typ").read_text(encoding="utf-8")
    # no sessions and no response profile -> those sections are absent
    assert "Tendances de charge" not in source
    assert "Synthèse de la réponse" not in source


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_report_with_sections_compiles_end_to_end(tmp_path):
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nats", date=date(2026, 10, 3), kind="competition", priority="A", label="Championnat"
        ),
    )
    for day, rpe in ((1, 6), (3, 7), (5, 8)):
        append_session(
            tmp_path,
            SessionEntry(performed_at=datetime(2026, 7, day, 9, 0), rpe=rpe, duration_min=50),
        )
    save_response_profile(
        tmp_path,
        ResponseProfile(
            as_of=date(2026, 7, 12),
            goal_id="sub-45-10k",
            per_goal_measured_rate=MeasuredRate(value=0.012, n=6, window_weeks=6.0, r2=0.7),
            adherence_by_quality=[
                AdherenceQuality(
                    quality="endurance_easy",
                    done=9,
                    partial=1,
                    modified=0,
                    missed=1,
                    adherence_pct=82.0,
                )
            ],
            caveats=["mesuré sur six séances provisoires"],
        ),
    )
    result = render_report_files(tmp_path, mode="expert")
    assert result.pdf_path.exists()
    assert result.pdf_path.stat().st_size > 1000


def test_bare_digits_do_not_inject_references():
    from performance_agent.evidence.corpus import load_corpus  # noqa: PLC0415
    from performance_agent.reports.renderer import _citations_for  # noqa: PLC0415

    pmid_entry = next((e for e in load_corpus() if e.pmid), None)
    if pmid_entry is None:
        pytest.skip("no PMID entry in corpus")
    assert _citations_for(f"Session id {pmid_entry.pmid} logged.") == []


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_expert_report_with_real_corpus_citation_compiles(tmp_path):
    from performance_agent.evidence.corpus import load_corpus  # noqa: PLC0415 - test-local import

    entry = load_corpus()[0]
    locator = f"DOI: {entry.doi}" if entry.doi else f"PMID: {entry.pmid}"
    _seed_athlete(tmp_path, f"# Plan\nBloc force ({locator}).")
    result = render_report_files(tmp_path, mode="expert")
    assert result.pdf_path.exists()
    text = result.source_path.read_text(encoding="utf-8")
    assert "Références" in text  # expert mode, fr labels
