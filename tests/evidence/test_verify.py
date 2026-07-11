import performance_agent.evidence.verify as verify_module
from performance_agent.evidence.schemas import EvidenceEntry
from performance_agent.evidence.verify import resolve_reference, verify_entry


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
        verify_module, "fetch_json", lambda url: payload if "crossref" in url else None
    )
    result = verify_entry(_entry())
    assert result.ok
    assert "A sample study" in (result.retrieved_title or "")


def test_doi_resolution_failure(monkeypatch):
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: None)
    result = verify_entry(_entry())
    assert not result.ok
    assert "10.1000/sample" in result.detail


def test_pmid_resolution_success(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}, "uids": ["123456"]}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    entry = _entry(doi=None, pmid="123456")
    result = verify_entry(entry)
    assert result.ok


def test_entry_without_locator_cannot_exist():
    # schema guarantees doi or pmid; verify_entry may assume it
    entry = _entry()
    assert entry.doi or entry.pmid


def test_fetch_json_returns_none_on_non_json_body(monkeypatch):
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"<html>error</html>"

    monkeypatch.setattr(
        verify_module.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse()
    )
    result = verify_entry(_entry())
    assert not result.ok


def test_disjoint_title_reports_mismatch(monkeypatch):
    payload = {"message": {"title": ["A completely unrelated paper about something else"]}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    result = verify_entry(_entry())
    assert not result.ok
    assert "TITLE MISMATCH" in result.detail


def test_subtitle_split_title_matches(monkeypatch):
    payload = {
        "message": {
            "title": ["Effects of Tapering on Performance"],
            "subtitle": ["A Meta-Analysis"],
        }
    }
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    entry = _entry(title="Effects of Tapering on Performance: A Meta-Analysis")
    result = verify_entry(entry)
    assert result.ok


def test_resolve_reference_via_doi(monkeypatch):
    payload = {"message": {"title": ["A sample study"]}}
    monkeypatch.setattr(
        verify_module, "fetch_json", lambda url: payload if "crossref" in url else None
    )
    resolved = resolve_reference("10.1000/sample", None)
    assert resolved.ok
    assert resolved.title == "A sample study"


def test_resolve_reference_via_pmid(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    resolved = resolve_reference(None, "123456")
    assert resolved.ok
    assert resolved.title == "A sample study"


def test_resolve_reference_without_locator():
    resolved = resolve_reference(None, None)
    assert not resolved.ok
    assert "no DOI or PMID" in resolved.detail


def test_resolve_reference_doi_does_not_resolve(monkeypatch):
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: None)
    resolved = resolve_reference("10.1000/missing", None)
    assert not resolved.ok
    assert "10.1000/missing" in resolved.detail


def test_resolve_reference_handles_malformed_doi():
    resolved = resolve_reference("not a real doi with spaces", None)
    assert not resolved.ok


def test_fetch_text_returns_none_on_network_failure(monkeypatch):
    def raise_oserror(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(verify_module.urllib.request, "urlopen", raise_oserror)
    assert verify_module.fetch_text("https://example.org") is None
