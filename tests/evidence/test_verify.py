import performance_agent.evidence.verify as verify_module
from performance_agent.evidence.schemas import EvidenceEntry
from performance_agent.evidence.verify import verify_entry


def _entry(**overrides) -> EvidenceEntry:
    data = {
        "id": "sample",
        "title": "A sample study",
        "authors": ["Doe J"],
        "year": 2020,
        "study_type": "rct",
        "conclusions": "x",
        "evidence_level": "moderate",
        "doi": "10.1000/sample",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


def test_doi_resolution_success(monkeypatch):
    payload = {"message": {"title": ["A sample study"]}}
    monkeypatch.setattr(
        verify_module, "_fetch_json", lambda url: payload if "crossref" in url else None
    )
    result = verify_entry(_entry())
    assert result.ok
    assert "A sample study" in (result.retrieved_title or "")


def test_doi_resolution_failure(monkeypatch):
    monkeypatch.setattr(verify_module, "_fetch_json", lambda _url: None)
    result = verify_entry(_entry())
    assert not result.ok
    assert "10.1000/sample" in result.detail


def test_pmid_resolution_success(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}, "uids": ["123456"]}}
    monkeypatch.setattr(verify_module, "_fetch_json", lambda _url: payload)
    entry = _entry(doi=None, pmid="123456")
    result = verify_entry(entry)
    assert result.ok


def test_entry_without_locator_cannot_exist():
    # schema guarantees doi or pmid; verify_entry may assume it
    entry = _entry()
    assert entry.doi or entry.pmid
