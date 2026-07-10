from performance_agent.evidence.index import EvidenceIndex
from performance_agent.evidence.schemas import EvidenceEntry, EvidenceLevel, StudyType


def _entry(entry_id: str, title: str, conclusions: str, **overrides) -> EvidenceEntry:
    data = {
        "id": entry_id,
        "title": title,
        "authors": ["Doe J"],
        "year": 2020,
        "study_type": "rct",
        "conclusions": conclusions,
        "evidence_level": "moderate",
        "doi": f"10.1000/{entry_id}",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


ENTRIES = [
    _entry(
        "strength-economy",
        "Strength training improves running economy",
        "Heavy strength training improves running economy in trained runners.",
        study_type="meta_analysis",
        evidence_level="strong",
    ),
    _entry(
        "taper-performance",
        "Tapering and competition performance",
        "Two-week exponential tapers improve endurance performance.",
    ),
    _entry(
        "stretching-injury",
        "Static stretching and injury risk",
        "Static stretching shows no clear effect on injury incidence.",
        study_type="cross_sectional",
        evidence_level="limited",
    ),
]


def test_search_finds_by_content_and_ranks_relevant_first():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("running economy strength")
    assert hits
    assert hits[0].entry.id == "strength-economy"


def test_stemmed_variants_match():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("taper")
    assert hits
    assert hits[0].entry.id == "taper-performance"


def test_search_respects_limit():
    index = EvidenceIndex(ENTRIES)
    assert len(index.search("performance training injury", limit=1)) == 1


def test_search_filters_by_study_type():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("training", study_type=StudyType.META_ANALYSIS)
    assert all(h.entry.study_type is StudyType.META_ANALYSIS for h in hits)


def test_search_filters_by_min_level():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("injury stretching", min_level=EvidenceLevel.MODERATE)
    accepted = {EvidenceLevel.MODERATE, EvidenceLevel.STRONG}
    assert all(h.entry.evidence_level in accepted for h in hits)


def test_no_hits_is_an_empty_list_not_an_error():
    index = EvidenceIndex(ENTRIES)
    assert index.search("quantum chromodynamics") == []


def test_hostile_query_syntax_does_not_crash():
    index = EvidenceIndex(ENTRIES)
    for query in ['"unbalanced', "AND OR NOT", "col:umn", "a*b(c)", "   "]:
        index.search(query)  # must not raise


def test_empty_query_returns_empty():
    index = EvidenceIndex(ENTRIES)
    assert index.search("") == []
