import pytest

from performance_agent.evidence.personal_corpus import (
    append_entry,
    load_personal_entries,
    personal_corpus_path,
)
from performance_agent.evidence.schemas import EvidenceEntry


def _entry(**overrides) -> EvidenceEntry:
    data = {
        "id": "live-sample",
        "title": "A live-found study",
        "authors": ["Doe J"],
        "year": 2022,
        "study_type": "rct",
        "conclusions": "x",
        "evidence_level": "moderate",
        "doi": "10.1000/live-sample",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


def test_load_personal_entries_empty_when_file_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    assert load_personal_entries() == []


def test_append_entry_creates_file_and_is_loadable(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    path = append_entry(_entry(), known_ids=set())
    assert path == personal_corpus_path()
    assert [e.id for e in load_personal_entries()] == ["live-sample"]


def test_append_entry_rejects_known_id(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="live-sample"):
        append_entry(_entry(), known_ids={"live-sample"})


def test_append_entry_preserves_previous_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    append_entry(_entry(id="live-one", doi="10.1000/one"), known_ids=set())
    append_entry(_entry(id="live-two", doi="10.1000/two"), known_ids={"live-one"})
    assert [e.id for e in load_personal_entries()] == ["live-one", "live-two"]
