import shutil
from datetime import date

import pytest

from performance_agent.memory.schemas import Goal, Profile
from performance_agent.memory.store import save_program, upsert_goal, write_profile
from performance_agent.reports.renderer import render_report_files

TODAY = date(2026, 7, 10)
HAS_TYPST = shutil.which("typst") is not None


def _seed_athlete(tmp_path, body: str) -> None:
    write_profile(tmp_path, Profile(locale="fr", display_name="Clément"))
    upsert_goal(tmp_path, Goal(id="sub-45-10k", statement="10 km sous 45:00"))
    save_program(tmp_path, body, "sub-45-10k", today=TODAY)


def test_fabricated_reference_aborts_before_any_file_is_written(tmp_path):
    _seed_athlete(tmp_path, "# Plan\nProuvé par la science (doi:10.9999/fake).")
    with pytest.raises(ValueError, match="10.9999/fake"):  # noqa: RUF043 - literal DOI, "." matches "."
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
def test_expert_report_with_real_corpus_citation_compiles(tmp_path):
    from performance_agent.evidence.corpus import load_corpus  # noqa: PLC0415 - test-local import

    entry = load_corpus()[0]
    locator = f"DOI: {entry.doi}" if entry.doi else f"PMID: {entry.pmid}"
    _seed_athlete(tmp_path, f"# Plan\nBloc force ({locator}).")
    result = render_report_files(tmp_path, mode="expert")
    assert result.pdf_path.exists()
    text = result.source_path.read_text(encoding="utf-8")
    assert "Références" in text  # expert mode, fr labels
