"""MCP wrappers over the documentation folder."""

import pytest

from performance_agent.server import document_tools


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def test_list_creates_folder_and_reports_new(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "study.pdf").write_bytes(b"x")
    inventory = document_tools.list_athlete_documents()
    assert [item["filename"] for item in inventory["new"]] == ["study.pdf"]
    assert (athlete_dir / "documentation" / "README.md").exists()


def test_mark_validates_evidence_ids_against_corpus(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "study.pdf").write_bytes(b"x")
    with pytest.raises(ValueError, match="not-a-corpus-id"):
        document_tools.mark_document_processed(
            "study.pdf", lane="evidence", summary="s", evidence_ids=["not-a-corpus-id"]
        )


def test_mark_context_then_list_shows_processed(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "notes.md").write_bytes(b"physio notes")
    result = document_tools.mark_document_processed(
        "notes.md", lane="context", summary="Physio: avoid loaded flexion 2 weeks."
    )
    assert result["lane"] == "context"
    inventory = document_tools.list_athlete_documents()
    assert inventory["processed"][0]["summary"] == "Physio: avoid loaded flexion 2 weeks."
