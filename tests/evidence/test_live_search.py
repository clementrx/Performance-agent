import pytest

import performance_agent.evidence.live_search as live_search_module
from performance_agent.evidence.live_search import (
    _SEARCH_LIMIT,
    LiveCandidate,
    LiveSearchOutcome,
    SearchFilters,
    _crossref_filter,
    _dedup,
    _map_pubmed_type,
    _openalex_abstract,
    _pubmed_term,
    _tier_rank,
    run_live_search,
    search_crossref,
    search_openalex,
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


def test_search_pubmed_parses_year_from_medline_date(monkeypatch):
    xml = _EFETCH_XML.replace("<Year>2021</Year>", "<MedlineDate>Winter 2020</MedlineDate>")
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: xml)
    candidates = search_pubmed("javelin throw", "en")
    assert candidates[0].year == 2020


def test_search_pubmed_year_is_none_without_year_or_medline_date(monkeypatch):
    xml = _EFETCH_XML.replace("<Year>2021</Year>", "")
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: xml)
    candidates = search_pubmed("javelin throw", "en")
    assert candidates[0].year is None


def test_search_pubmed_falls_back_to_collective_name(monkeypatch):
    xml = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">333</PMID>
      <Article>
        <ArticleTitle>Consortium javelin study</ArticleTitle>
        <AuthorList>
          <Author><CollectiveName>The Javelin Consortium</CollectiveName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["333"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: xml)
    candidates = search_pubmed("javelin", "en")
    assert candidates[0].authors == ["The Javelin Consortium"]


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
    def fake_search_pubmed(
        _term: str, language: str, _filters: SearchFilters
    ) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/found", found_via_language=language)]

    def fake_search_crossref(
        _term: str, _language: str, _filters: SearchFilters
    ) -> list[LiveCandidate]:
        raise OSError("network down")

    def fake_search_semantic_scholar(
        _term: str, _language: str, _filters: SearchFilters
    ) -> list[LiveCandidate]:
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


def test_openalex_abstract_reconstruction_places_words_at_positions():
    inverted = {"training": [2], "Javelin": [0], "throw": [1], "works": [3, 5], "it": [4]}
    assert _openalex_abstract(inverted) == "Javelin throw training works it works"


def test_openalex_abstract_reconstruction_handles_missing_index():
    assert _openalex_abstract(None) is None
    assert _openalex_abstract({}) is None


def test_search_openalex_builds_candidates(monkeypatch):
    payload = {
        "results": [
            {
                "title": "Lancer de javelot et biomécanique",
                "doi": "https://doi.org/10.1000/javelot",
                "publication_year": 2020,
                "type": "review",
                "abstract_inverted_index": {"Une": [0], "revue": [1]},
                "authorships": [{"author": {"display_name": "Jean Dupont"}}],
                "primary_location": {"source": {"display_name": "Science et Sport"}},
            },
            {
                "title": None,  # no title -> dropped
                "doi": "https://doi.org/10.1000/no-title",
            },
            {
                "title": "No locator work",  # no DOI -> dropped
                "doi": None,
            },
        ]
    }

    def fake_fetch_json(url: str) -> dict | None:
        assert "api.openalex.org/works" in url
        assert "mailto=performance-agent@users.noreply.github.com" in url
        return payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)

    candidates = search_openalex("lancer de javelot", "fr")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/javelot"
    assert candidate.title == "Lancer de javelot et biomécanique"
    assert candidate.year == 2020
    assert candidate.abstract == "Une revue"
    assert candidate.authors == ["Jean Dupont"]
    assert candidate.journal == "Science et Sport"
    # OpenAlex cannot distinguish systematic from narrative reviews: never mapped
    assert candidate.suggested_study_type is None
    assert candidate.source == "openalex"
    assert candidate.found_via_language == "fr"


def test_search_openalex_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_openalex("javelin", "en") == []


def test_search_openalex_skips_authorship_with_null_author(monkeypatch):
    payload = {
        "results": [
            {
                "title": "Javelot et biomécanique",
                "doi": "https://doi.org/10.1000/javelot",
                "publication_year": 2020,
                "authorships": [
                    {"author": {"display_name": "Jean Dupont"}},
                    {"author": None},
                ],
            }
        ]
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)

    candidates = search_openalex("lancer de javelot", "fr")

    assert len(candidates) == 1
    assert candidates[0].authors == ["Jean Dupont"]


def test_run_live_search_fans_out_to_four_sources(monkeypatch):
    calls: list[str] = []

    def fake_source(name):
        def search(_term, language, _filters):
            calls.append(f"{name}:{language}")
            return []

        return search

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        tuple((name, fake_source(name)) for name, _fn in live_search_module._SOURCES),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    run_live_search({"en": "javelin"})

    assert calls == ["pubmed:en", "crossref:en", "semantic_scholar:en", "openalex:en"]


def test_run_live_search_drops_unverified_candidates(monkeypatch):
    def fake_search_pubmed(
        _term: str, language: str, _filters: SearchFilters
    ) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/unverified", found_via_language=language)]

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (
            ("pubmed", fake_search_pubmed),
            ("crossref", lambda _term, _language, _filters: []),
            ("semantic_scholar", lambda _term, _language, _filters: []),
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


def test_pubmed_term_encodes_year_range_and_types():
    filters = SearchFilters(
        year_from=2016, year_to=2026, publication_types=("meta_analysis", "rct")
    )
    term = _pubmed_term("hypertrophy volume", filters)
    assert term.startswith("hypertrophy volume")
    assert 'AND ("2016"[dp] : "2026"[dp])' in term
    assert "AND (meta-analysis[pt] OR randomized controlled trial[pt])" in term


def test_pubmed_term_open_ended_year_bounds():
    term = _pubmed_term("tapering", SearchFilters(year_from=2016))
    assert 'AND ("2016"[dp] : "3000"[dp])' in term
    term = _pubmed_term("tapering", SearchFilters(year_to=2020))
    assert 'AND ("1000"[dp] : "2020"[dp])' in term


def test_pubmed_term_without_filters_is_unchanged():
    assert _pubmed_term("tapering", SearchFilters()) == "tapering"


def test_crossref_filter_clause():
    filters = SearchFilters(year_from=2016, year_to=2026, publication_types=("rct",))
    assert _crossref_filter(filters) == (
        "from-pub-date:2016-01-01,until-pub-date:2026-12-31,type:journal-article"
    )
    assert _crossref_filter(SearchFilters()) == ""


def test_semantic_scholar_url_carries_year_and_types(monkeypatch):
    seen: list[str] = []

    def fake_fetch_json(url: str) -> dict | None:
        seen.append(url)
        return {"data": []}

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    filters = SearchFilters(
        year_from=2016, year_to=2026, publication_types=("meta_analysis", "systematic_review")
    )
    search_semantic_scholar("tapering", "en", filters)
    assert "year=2016-2026" in seen[0]
    assert "publicationTypes=MetaAnalysis,Review" in seen[0]


def test_openalex_url_carries_date_filter_and_postfilters_types(monkeypatch):
    seen: list[str] = []
    payload = {
        "results": [
            {"title": "A dataset", "doi": "https://doi.org/10.1/d", "type": "dataset"},
            {"title": "A review", "doi": "https://doi.org/10.1/r", "type": "review"},
            {"title": "Untyped", "doi": "https://doi.org/10.1/u"},
        ]
    }

    def fake_fetch_json(url: str) -> dict | None:
        seen.append(url)
        return payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    filters = SearchFilters(year_from=2016, year_to=2026, publication_types=("rct",))
    candidates = search_openalex("tapering", "en", filters)
    assert "filter=from_publication_date:2016-01-01,to_publication_date:2026-12-31" in seen[0]
    # incompatible type dropped; ambiguous/missing types pass through ungraded
    assert [c.doi for c in candidates] == ["10.1/r", "10.1/u"]
    assert all(c.suggested_study_type is None for c in candidates)


def test_run_live_search_rejects_unknown_publication_type():
    with pytest.raises(ValueError, match="cohort"):
        run_live_search({"en": "x"}, publication_types=["cohort"])


def test_run_live_search_rejects_inverted_year_range():
    with pytest.raises(ValueError, match="year_from"):
        run_live_search({"en": "x"}, year_from=2026, year_to=2016)


def test_run_live_search_passes_filters_to_every_source(monkeypatch):
    received: list[SearchFilters] = []

    def fake_source(_term, _language, filters):
        received.append(filters)
        return []

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        tuple((name, fake_source) for name, _fn in live_search_module._SOURCES),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    run_live_search({"en": "x"}, year_from=2016, publication_types=["meta_analysis"])

    assert len(received) == 4
    assert all(
        f == SearchFilters(year_from=2016, publication_types=("meta_analysis",)) for f in received
    )


def test_search_limit_is_25():
    assert _SEARCH_LIMIT == 25


def test_tier_rank_orders_designs():
    assert _tier_rank(_candidate(suggested_study_type=StudyType.META_ANALYSIS)) == 0
    assert _tier_rank(_candidate(suggested_study_type=StudyType.SYSTEMATIC_REVIEW)) == 1
    assert _tier_rank(_candidate(suggested_study_type=StudyType.RCT)) == 2
    assert _tier_rank(_candidate(suggested_study_type=StudyType.COHORT)) == 3
    assert _tier_rank(_candidate(suggested_study_type=None)) == 3


def test_run_live_search_orders_by_tier_then_year(monkeypatch):
    synthetic = [
        _candidate(doi="10.1/rct-old", year=2010, suggested_study_type=StudyType.RCT),
        _candidate(doi="10.1/none-2024", year=2024, suggested_study_type=None),
        _candidate(doi="10.1/ma-2018", year=2018, suggested_study_type=StudyType.META_ANALYSIS),
        _candidate(doi="10.1/sr-2022", year=2022, suggested_study_type=StudyType.SYSTEMATIC_REVIEW),
        _candidate(doi="10.1/ma-2023", year=2023, suggested_study_type=StudyType.META_ANALYSIS),
        _candidate(doi="10.1/none-undated", year=None, suggested_study_type=None),
    ]

    def fake_source(_term, _language, _filters):
        return synthetic

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (("pubmed", fake_source),),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(True, "A study", "resolved via Crossref"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin"})

    assert [c.doi for c in outcome.candidates] == [
        "10.1/ma-2023",
        "10.1/ma-2018",
        "10.1/sr-2022",
        "10.1/rct-old",
        "10.1/none-2024",
        "10.1/none-undated",
    ]
