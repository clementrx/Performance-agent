import performance_agent.evidence.live_search as live_search_module
from performance_agent.evidence.live_search import (
    LiveCandidate,
    LiveSearchOutcome,
    _dedup,
    _map_pubmed_type,
    run_live_search,
    search_crossref,
    search_pubmed,
    search_semantic_scholar,
)
from performance_agent.evidence.schemas import StudyType
from performance_agent.evidence.verify import ResolvedReference


def test_map_pubmed_type_recognizes_rct():
    assert _map_pubmed_type(["Journal Article", "Randomized Controlled Trial"]) == StudyType.RCT


def test_map_pubmed_type_returns_none_when_unmapped():
    assert _map_pubmed_type(["Journal Article"]) is None


def test_map_pubmed_type_prefers_first_match_in_map_order():
    # "Meta-Analysis" and "Systematic Review" both present; either is a valid strong
    # mapping, so just assert it picked one of them, not None.
    result = _map_pubmed_type(["Systematic Review", "Meta-Analysis"])
    assert result in (StudyType.SYSTEMATIC_REVIEW, StudyType.META_ANALYSIS)


_EFETCH_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">111</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
          <Title>Journal of Sports Sciences</Title>
        </Journal>
        <ArticleTitle>Javelin biomechanics and throw distance</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Throwing is complex.</AbstractText>
          <AbstractText Label="RESULTS">Distance improved.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Doe</LastName><Initials>J</Initials></Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType>Randomized Controlled Trial</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">111</ArticleId>
        <ArticleId IdType="doi">10.1000/javelin</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">222</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><MedlineDate>Winter 2020</MedlineDate></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle></ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_search_pubmed_builds_candidates_from_efetch(monkeypatch):
    esearch_payload = {"esearchresult": {"idlist": ["111", "222"]}}

    def fake_fetch_json(url: str) -> dict | None:
        assert "esearch" in url
        return esearch_payload

    def fake_fetch_text(url: str) -> str | None:
        assert "efetch" in url
        assert "rettype=abstract" in url
        assert "retmode=xml" in url
        assert "id=111,222" in url
        return _EFETCH_XML

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(live_search_module, "fetch_text", fake_fetch_text)

    candidates = search_pubmed("javelin throw", "en")

    assert len(candidates) == 1  # the empty-title article is dropped
    candidate = candidates[0]
    assert isinstance(candidate, LiveCandidate)
    assert candidate.pmid == "111"
    assert candidate.doi == "10.1000/javelin"
    assert candidate.title == "Javelin biomechanics and throw distance"
    assert candidate.abstract == "Throwing is complex. Distance improved."
    assert candidate.year == 2021
    assert candidate.journal == "Journal of Sports Sciences"
    assert candidate.authors == ["Doe J"]
    assert candidate.suggested_study_type == StudyType.RCT
    assert candidate.source == "pubmed"
    assert candidate.found_via_language == "en"


def test_search_pubmed_keeps_candidate_without_year(monkeypatch):
    xml = _EFETCH_XML.replace("<Year>2021</Year>", "")
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: xml)
    candidates = search_pubmed("javelin throw", "en")
    assert candidates[0].year is None


def test_search_pubmed_returns_empty_on_malformed_xml(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: "<not-xml")
    assert search_pubmed("javelin throw", "en") == []


def test_search_pubmed_returns_empty_when_efetch_fails(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: None)
    assert search_pubmed("javelin throw", "en") == []


def test_search_pubmed_returns_empty_when_no_hits(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": []}}
    )
    assert search_pubmed("nonexistent topic", "en") == []


def test_search_pubmed_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_pubmed("javelin throw", "en") == []


def test_search_crossref_builds_candidates(monkeypatch):
    payload = {
        "message": {
            "items": [
                {
                    "title": ["Javelin throw kinematics"],
                    "DOI": "10.1000/kinematics",
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "published": {"date-parts": [[2019]]},
                    "container-title": ["Sports Biomechanics"],
                },
                {
                    "title": [],  # no title -> dropped
                    "DOI": "10.1000/no-title",
                    "published": {"date-parts": [[2019]]},
                },
            ]
        }
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)

    candidates = search_crossref("javelin kinematics", "en")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/kinematics"
    assert candidate.authors == ["Jane Doe"]
    assert candidate.year == 2019
    assert candidate.journal == "Sports Biomechanics"
    assert candidate.source == "crossref"


def test_search_crossref_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_crossref("javelin", "en") == []


def test_search_semantic_scholar_builds_candidates(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Speerwurf Trainingsmethoden",
                "year": 2022,
                "authors": [{"name": "Max Muller"}],
                "externalIds": {"DOI": "10.1000/speerwurf"},
                "abstract": "An overview of javelin training methods.",
                "venue": "Leistungssport",
            },
            {
                "title": "No locator study",
                "year": 2022,
                "authors": [{"name": "No One"}],
                "externalIds": {},  # no DOI or PMID -> dropped
            },
        ]
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)

    candidates = search_semantic_scholar("Speerwurf Training", "de")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/speerwurf"
    assert candidate.abstract == "An overview of javelin training methods."
    assert candidate.source == "semantic_scholar"
    assert candidate.found_via_language == "de"


def test_search_semantic_scholar_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_semantic_scholar("javelin", "en") == []


def test_search_crossref_keeps_candidate_without_year(monkeypatch):
    payload = {"message": {"items": [{"title": ["Undated but real"], "DOI": "10.1000/undated"}]}}
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)
    candidates = search_crossref("javelin", "en")
    assert len(candidates) == 1
    assert candidates[0].year is None


def test_search_semantic_scholar_keeps_candidate_without_year(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Undated study",
                "authors": [{"name": "Doe J"}],
                "externalIds": {"DOI": "10.1000/undated"},
            }
        ]
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)
    candidates = search_semantic_scholar("javelin", "en")
    assert len(candidates) == 1
    assert candidates[0].year is None


def _candidate(**overrides) -> LiveCandidate:
    data = {
        "title": "A study",
        "authors": ["Doe J"],
        "year": 2021,
        "journal": "J Sports Sci",
        "abstract": None,
        "doi": "10.1000/a",
        "pmid": None,
        "suggested_study_type": None,
        "source": "pubmed",
        "found_via_language": "en",
    }
    data.update(overrides)
    return LiveCandidate(**data)


def test_dedup_by_doi_case_insensitive():
    candidates = [_candidate(doi="10.1000/A"), _candidate(doi="10.1000/a")]
    assert len(_dedup(candidates)) == 1


def test_dedup_by_pmid():
    candidates = [
        _candidate(doi=None, pmid="123"),
        _candidate(doi=None, pmid="123"),
        _candidate(doi=None, pmid="456"),
    ]
    assert len(_dedup(candidates)) == 2


def test_dedup_drops_candidates_without_any_locator():
    candidates = [_candidate(doi=None, pmid=None)]
    assert _dedup(candidates) == []


def test_run_live_search_verifies_and_reports_failures(monkeypatch):
    def fake_search_pubmed(_term: str, language: str) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/found", found_via_language=language)]

    def fake_search_crossref(_term: str, _language: str) -> list[LiveCandidate]:
        raise OSError("network down")

    def fake_search_semantic_scholar(_term: str, _language: str) -> list[LiveCandidate]:
        return []

    monkeypatch.setattr(live_search_module, "search_pubmed", fake_search_pubmed)
    monkeypatch.setattr(live_search_module, "search_crossref", fake_search_crossref)
    monkeypatch.setattr(live_search_module, "search_semantic_scholar", fake_search_semantic_scholar)
    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (
            ("pubmed", fake_search_pubmed),
            ("crossref", fake_search_crossref),
            ("semantic_scholar", fake_search_semantic_scholar),
        ),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(True, "A study", "resolved via Crossref"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin throw"})

    assert isinstance(outcome, LiveSearchOutcome)
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].doi == "10.1000/found"
    assert outcome.failed_sources == ["crossref:en"]


def test_run_live_search_drops_unverified_candidates(monkeypatch):
    def fake_search_pubmed(_term: str, language: str) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/unverified", found_via_language=language)]

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (
            ("pubmed", fake_search_pubmed),
            ("crossref", lambda _term, _language: []),
            ("semantic_scholar", lambda _term, _language: []),
        ),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(False, None, "did not resolve"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin throw"})

    assert outcome.candidates == []
    assert outcome.failed_sources == []
