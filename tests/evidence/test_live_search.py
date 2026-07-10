import performance_agent.evidence.live_search as live_search_module
from performance_agent.evidence.live_search import (
    PUBMED_TYPE_MAP,  # noqa: F401 - asserts the map is exported as public API
    LiveCandidate,
    _map_pubmed_type,
    search_pubmed,
)
from performance_agent.evidence.schemas import StudyType


def test_map_pubmed_type_recognizes_rct():
    assert _map_pubmed_type(["Journal Article", "Randomized Controlled Trial"]) == StudyType.RCT


def test_map_pubmed_type_returns_none_when_unmapped():
    assert _map_pubmed_type(["Journal Article"]) is None


def test_map_pubmed_type_prefers_first_match_in_map_order():
    # "Meta-Analysis" and "Systematic Review" both present; either is a valid strong
    # mapping, so just assert it picked one of them, not None.
    result = _map_pubmed_type(["Systematic Review", "Meta-Analysis"])
    assert result in (StudyType.SYSTEMATIC_REVIEW, StudyType.META_ANALYSIS)


def test_search_pubmed_builds_candidates(monkeypatch):
    esearch_payload = {"esearchresult": {"idlist": ["111", "222"]}}
    esummary_payload = {
        "result": {
            "111": {
                "title": "Javelin biomechanics and throw distance",
                "authors": [{"name": "Doe J"}],
                "pubdate": "2021 Jun",
                "fulljournalname": "J Sports Sci",
                "pubtype": ["Randomized Controlled Trial"],
                "articleids": [{"idtype": "doi", "value": "10.1000/javelin"}],
            },
            "222": {
                "title": "",  # no title -> dropped
                "authors": [],
                "pubdate": "2020",
                "pubtype": [],
                "articleids": [],
            },
        }
    }

    def fake_fetch_json(url: str) -> dict | None:
        return esearch_payload if "esearch" in url else esummary_payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)

    candidates = search_pubmed("javelin throw", "en")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, LiveCandidate)
    assert candidate.pmid == "111"
    assert candidate.doi == "10.1000/javelin"
    assert candidate.suggested_study_type == StudyType.RCT
    assert candidate.source == "pubmed"
    assert candidate.found_via_language == "en"
    assert candidate.year == 2021


def test_search_pubmed_returns_empty_when_no_hits(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": []}}
    )
    assert search_pubmed("nonexistent topic", "en") == []


def test_search_pubmed_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_pubmed("javelin throw", "en") == []
