import pytest
from pydantic import ValidationError

from performance_agent.evidence.schemas import (
    STARS,
    EvidenceEntry,
    EvidenceLevel,
    StudyType,
)

VALID = {
    "id": "example-meta-analysis",
    "title": "An example meta-analysis",
    "authors": ["Doe J", "Roe R"],
    "year": 2020,
    "study_type": "meta_analysis",
    "conclusions": "Something robust.",
    "evidence_level": "strong",
    "doi": "10.1000/example",
}


def test_valid_entry_round_trips():
    entry = EvidenceEntry.model_validate(VALID)
    assert entry.study_type is StudyType.META_ANALYSIS
    assert entry.evidence_level is EvidenceLevel.STRONG
    assert entry.verified is False


@pytest.mark.parametrize(
    ("study_type", "too_high"),
    [
        ("cross_sectional", "strong"),
        ("cross_sectional", "moderate"),
        ("rct", "strong"),
        ("cohort", "strong"),
        ("expert_opinion", "limited"),
    ],
)
def test_grading_ceilings_are_enforced(study_type, too_high):
    with pytest.raises(ValidationError, match="ceiling"):
        EvidenceEntry.model_validate(
            {**VALID, "study_type": study_type, "evidence_level": too_high}
        )


@pytest.mark.parametrize(
    ("study_type", "level"),
    [
        ("systematic_review", "strong"),
        ("meta_analysis", "strong"),
        ("rct", "moderate"),
        ("cross_sectional", "limited"),
        ("expert_opinion", "expert"),
        ("meta_analysis", "limited"),  # grading BELOW the ceiling is always allowed
    ],
)
def test_levels_at_or_below_ceiling_are_accepted(study_type, level):
    entry = EvidenceEntry.model_validate(
        {**VALID, "study_type": study_type, "evidence_level": level}
    )
    assert entry.evidence_level is EvidenceLevel(level)


def test_an_entry_needs_a_doi_or_pmid():
    data = {**VALID}
    del data["doi"]
    with pytest.raises(ValidationError, match="DOI or a PMID"):
        EvidenceEntry.model_validate(data)


def test_pmid_alone_is_enough():
    data = {**VALID}
    del data["doi"]
    entry = EvidenceEntry.model_validate({**data, "pmid": "11708692"})
    assert entry.pmid == "11708692"


def test_stars_cover_every_level():
    assert set(STARS) == set(EvidenceLevel)
    assert STARS[EvidenceLevel.STRONG] == "★★★★★"
    assert STARS[EvidenceLevel.EXPERT] == "★☆☆☆☆"


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        EvidenceEntry.model_validate({**VALID, "impact_factor": 42})
