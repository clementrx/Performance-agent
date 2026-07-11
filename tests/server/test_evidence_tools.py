"""In-process tests for the evidence MCP tools (real packaged corpus)."""

import pytest

import performance_agent.evidence.verify as verify_module
import performance_agent.server.evidence_tools as evidence_tools_module
from performance_agent.evidence.live_search import LiveCandidate, LiveSearchOutcome
from performance_agent.evidence.schemas import StudyType
from performance_agent.evidence.verify import ResolvedReference


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    evidence_tools_module._index.cache_clear()
    yield tmp_path
    evidence_tools_module._index.cache_clear()


@pytest.mark.anyio
async def test_search_evidence_returns_graded_hits(client):
    result = await client.call_tool("search_evidence", {"query": "strength training"})
    assert not result.isError
    hits = result.structuredContent["hits"]
    assert hits, "the live-verified starter corpus must match a strength query"
    first = hits[0]
    assert set(first) >= {
        "id",
        "title",
        "year",
        "study_type",
        "evidence_level",
        "stars",
        "conclusions",
        "citation",
    }
    assert first["stars"].count("★") + first["stars"].count("☆") == 5


@pytest.mark.anyio
async def test_search_evidence_empty_result_is_not_an_error(client):
    result = await client.call_tool("search_evidence", {"query": "quantum chromodynamics"})
    assert not result.isError
    assert result.structuredContent["hits"] == []


@pytest.mark.anyio
async def test_get_citation_by_id(client):
    search = await client.call_tool("search_evidence", {"query": "strength training"})
    entry_id = search.structuredContent["hits"][0]["id"]
    result = await client.call_tool("get_citation", {"evidence_id": entry_id})
    assert not result.isError
    assert result.structuredContent["citation"]
    assert result.structuredContent["stars"]


@pytest.mark.anyio
async def test_get_citation_unknown_id_is_readable_error(client):
    result = await client.call_tool("get_citation", {"evidence_id": "no-such-entry"})
    assert result.isError
    assert "search_evidence" in result.content[0].text


@pytest.mark.anyio
async def test_check_citations_flags_fabrications(client):
    result = await client.call_tool(
        "check_citations", {"text": "Proven by science (doi:10.9999/fabricated)."}
    )
    assert not result.isError
    report = result.structuredContent
    assert report["ok"] is False
    assert "10.9999/fabricated" in report["unknown_references"]


@pytest.mark.anyio
async def test_check_citations_passes_clean_text(client):
    result = await client.call_tool("check_citations", {"text": "Squat 5x5 at 80%."})
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["unknown_references"] == []


@pytest.mark.anyio
async def test_search_filters_work_through_the_tool(client):
    result = await client.call_tool("search_evidence", {"query": "training", "min_level": "strong"})
    assert not result.isError
    hits = result.structuredContent["hits"]
    assert hits, "at least one strong entry should match 'training'"
    assert all(hit["evidence_level"] == "strong" for hit in hits)


@pytest.mark.anyio
async def test_evidence_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {"search_evidence", "get_citation", "check_citations"} <= names


@pytest.mark.anyio
async def test_search_evidence_live_returns_verified_candidates(client, monkeypatch):
    def fake_run_live_search(_language_terms, **_filter_kwargs):
        return LiveSearchOutcome(
            candidates=[
                LiveCandidate(
                    title="Javelin throw training review",
                    authors=["Doe J"],
                    year=2021,
                    journal="J Sports Sci",
                    abstract=None,
                    doi="10.1000/javelin-review",
                    pmid=None,
                    suggested_study_type=StudyType.SYSTEMATIC_REVIEW,
                    source="pubmed",
                    found_via_language="en",
                )
            ],
            failed_sources=["crossref:de"],
        )

    monkeypatch.setattr(evidence_tools_module, "run_live_search", fake_run_live_search)

    result = await client.call_tool(
        "search_evidence_live", {"language_terms": {"en": "javelin throw training"}}
    )

    assert not result.isError
    body = result.structuredContent
    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["doi"] == "10.1000/javelin-review"
    assert candidate["suggested_study_type"] == "systematic_review"
    assert body["failed_sources"] == ["crossref:de"]


@pytest.mark.anyio
async def test_search_evidence_live_is_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert "search_evidence_live" in names


@pytest.mark.anyio
async def test_verify_reference_resolves_doi(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            True, "A federation whitepaper", "resolved via Crossref"
        ),
    )
    result = await client.call_tool("verify_reference", {"doi": "10.1000/whitepaper"})
    assert not result.isError
    assert result.structuredContent == {
        "ok": True,
        "title": "A federation whitepaper",
        "detail": "resolved via Crossref",
    }


@pytest.mark.anyio
async def test_verify_reference_reports_failure_without_raising(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(False, None, "DOI did not resolve: 10.1000/fake"),
    )
    result = await client.call_tool("verify_reference", {"doi": "10.1000/fake"})
    assert not result.isError
    assert result.structuredContent["ok"] is False


@pytest.mark.anyio
async def test_verify_reference_handles_malformed_input_without_raising(client):
    result = await client.call_tool("verify_reference", {"doi": "not a real doi with spaces"})
    assert not result.isError
    assert result.structuredContent["ok"] is False


def _live_entry_payload(**overrides) -> dict:
    data = {
        "id": "live-javelin-review",
        "title": "Javelin throw training review",
        "authors": ["Doe J"],
        "year": 2021,
        "study_type": "systematic_review",
        "conclusions": "Periodized throwing volume improves distance over a macrocycle.",
        "evidence_level": "strong",
        "doi": "10.1000/javelin-review",
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_save_evidence_persists_and_is_immediately_searchable(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            True, "Javelin throw training review", "resolved via Crossref"
        ),
    )

    save_result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    assert not save_result.isError
    assert save_result.structuredContent["path"].endswith("evidence_extra.yaml")

    search_result = await client.call_tool("search_evidence", {"query": "javelin throw training"})
    ids = {hit["id"] for hit in search_result.structuredContent["hits"]}
    assert "live-javelin-review" in ids


@pytest.mark.anyio
async def test_save_evidence_rejects_unresolvable_locator(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            False, None, "DOI did not resolve: 10.1000/javelin-review"
        ),
    )

    result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    assert result.isError
    assert "could not verify" in result.content[0].text


@pytest.mark.anyio
async def test_save_evidence_rejects_grading_ceiling_violation(client):
    # a cross_sectional study cannot be graded "strong" — schemas.py enforces this
    result = await client.call_tool(
        "save_evidence",
        {
            "entry": _live_entry_payload(
                id="live-overgraded", study_type="cross_sectional", evidence_level="strong"
            )
        },
    )
    assert result.isError


@pytest.mark.anyio
async def test_save_evidence_rejects_id_collision(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            True, "Javelin throw training review", "resolved via Crossref"
        ),
    )
    await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    result = await client.call_tool(
        "save_evidence", {"entry": _live_entry_payload(doi="10.1000/other-doi")}
    )
    assert result.isError
    assert "live-javelin-review" in result.content[0].text


@pytest.mark.anyio
async def test_save_evidence_rejects_title_mismatch(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            True, "Completely Different Study About Fish", "resolved via Crossref"
        ),
    )

    result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})

    assert result.isError
    text = result.content[0].text
    assert "Javelin throw training review" in text
    assert "Completely Different Study About Fish" in text


@pytest.mark.anyio
async def test_search_evidence_live_forwards_filters(client, monkeypatch):
    received: dict = {}

    def fake_run_live_search(language_terms, year_from=None, year_to=None, publication_types=None):
        received.update(
            language_terms=language_terms,
            year_from=year_from,
            year_to=year_to,
            publication_types=publication_types,
        )
        return LiveSearchOutcome(candidates=[], failed_sources=[])

    monkeypatch.setattr(evidence_tools_module, "run_live_search", fake_run_live_search)

    result = await client.call_tool(
        "search_evidence_live",
        {
            "language_terms": {"en": "tapering"},
            "year_from": 2016,
            "year_to": 2026,
            "publication_types": ["meta_analysis", "rct"],
        },
    )
    assert not result.isError
    assert received == {
        "language_terms": {"en": "tapering"},
        "year_from": 2016,
        "year_to": 2026,
        "publication_types": ["meta_analysis", "rct"],
    }


@pytest.mark.anyio
async def test_search_evidence_live_rejects_bad_publication_type(client):
    result = await client.call_tool(
        "search_evidence_live",
        {"language_terms": {"en": "tapering"}, "publication_types": ["cohort"]},
    )
    assert result.isError
    assert "cohort" in result.content[0].text


_MANUEL_ULTIME = {
    "id": "book-manuel-ultime-musculation",
    "title": "Manuel ultime de musculation — Connaissances scientifiques et méthodologie",
    "authors": ["Pourcelot C", "Reiss D", "Caverne A", "Albignac T"],
    "year": 2023,
    "journal": "Éditions Amphora",
    "study_type": "reference_book",
    "conclusions": "Exercise-technique and pedagogy reference for strength training.",
    "evidence_level": "expert",
    "isbn": "978-2-7576-0546-2",
}


@pytest.mark.anyio
async def test_save_evidence_accepts_isbn_verified_reference_book(client, monkeypatch):
    def fake_fetch_json(url: str) -> dict | None:
        assert "openlibrary.org/isbn/9782757605462.json" in url
        return {"title": "Manuel ultime de musculation"}

    monkeypatch.setattr(verify_module, "fetch_json", fake_fetch_json)

    save_result = await client.call_tool("save_evidence", {"entry": _MANUEL_ULTIME})
    assert not save_result.isError
    assert save_result.structuredContent["path"].endswith("evidence_extra.yaml")

    search_result = await client.call_tool("search_evidence", {"query": "musculation"})
    ids = {hit["id"] for hit in search_result.structuredContent["hits"]}
    assert "book-manuel-ultime-musculation" in ids

    check = await client.call_tool(
        "check_citations", {"text": "Voir le Manuel ultime (ISBN 978-2-7576-0546-2)."}
    )
    assert check.structuredContent["ok"] is True


@pytest.mark.anyio
async def test_save_evidence_rejects_book_with_mismatched_title(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_isbn",
        lambda _isbn: ResolvedReference(
            True, "Completely Different Book About Fish", "resolved via Open Library"
        ),
    )
    result = await client.call_tool("save_evidence", {"entry": _MANUEL_ULTIME})
    assert result.isError
    assert "Completely Different Book About Fish" in result.content[0].text


@pytest.mark.anyio
async def test_verify_reference_resolves_isbn(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_isbn",
        lambda _isbn: ResolvedReference(
            True, "Manuel ultime de musculation", "resolved via Open Library"
        ),
    )
    result = await client.call_tool("verify_reference", {"isbn": "978-2-7576-0546-2"})
    assert not result.isError
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["title"] == "Manuel ultime de musculation"
