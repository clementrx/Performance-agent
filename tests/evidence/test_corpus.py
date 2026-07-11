import pytest

from performance_agent.evidence.corpus import load_corpus, parse_manifest

MANIFEST = """
- id: entry-one
  title: First entry
  authors: [Doe J]
  year: 2019
  study_type: rct
  conclusions: Something.
  evidence_level: moderate
  doi: 10.1000/one
- id: entry-two
  title: Second entry
  authors: [Roe R]
  year: 2021
  study_type: meta_analysis
  conclusions: Something else.
  evidence_level: strong
  pmid: "123456"
"""


def test_parse_manifest_returns_entries_in_order():
    entries = parse_manifest(MANIFEST)
    assert [e.id for e in entries] == ["entry-one", "entry-two"]


def test_duplicate_ids_are_rejected():
    duplicated = MANIFEST + MANIFEST.replace("entry-one", "entry-two", 1)
    with pytest.raises(ValueError, match="duplicate"):
        parse_manifest(duplicated)


def test_manifest_must_be_a_list():
    with pytest.raises(ValueError, match="list"):
        parse_manifest("id: not-a-list\n")


def test_packaged_corpus_loads_and_validates():
    entries = load_corpus()
    assert len(entries) >= 1
    assert all(entry.doi or entry.pmid for entry in entries)


def test_shipped_corpus_is_fully_verified():
    entries = load_corpus()
    assert all(entry.verified for entry in entries)
    assert "bootstrap-placeholder" not in {entry.id for entry in entries}
    assert len(entries) >= 8


def test_load_corpus_merges_personal_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    (tmp_path / "evidence_extra.yaml").write_text(
        """
- id: live-extra
  title: A personally discovered study
  authors: [Roe R]
  year: 2023
  study_type: cohort
  conclusions: Something new.
  evidence_level: moderate
  pmid: "999999"
""",
        encoding="utf-8",
    )
    ids = {e.id for e in load_corpus()}
    assert "live-extra" in ids


def test_load_corpus_without_personal_file_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    ids = {e.id for e in load_corpus()}
    assert "live-extra" not in ids
    assert len(ids) >= 8  # the packaged corpus alone


def test_load_corpus_rejects_id_collision_with_packaged(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    packaged_id = load_corpus()[0].id
    (tmp_path / "evidence_extra.yaml").write_text(
        f"""
- id: {packaged_id}
  title: Colliding id
  authors: [Roe R]
  year: 2023
  study_type: cohort
  conclusions: Something new.
  evidence_level: moderate
  pmid: "999999"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus()
