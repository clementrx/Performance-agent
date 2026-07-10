"""Schemas and grading rules for the evidence corpus.

The grading ceiling is the honesty rule of spec v2 §5: an entry's evidence
level can never exceed what its study design can support.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudyType(StrEnum):
    """Study designs, strongest first (spec v2 §1 hierarchy)."""

    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    RCT = "rct"
    COHORT = "cohort"
    CROSS_SECTIONAL = "cross_sectional"
    CONSENSUS = "consensus"
    EXPERT_OPINION = "expert_opinion"


class EvidenceLevel(StrEnum):
    """Graded strength of evidence, shown to athletes as stars."""

    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"
    EXPERT = "expert"


_LEVEL_RANK: dict[EvidenceLevel, int] = {
    EvidenceLevel.EXPERT: 0,
    EvidenceLevel.LIMITED: 1,
    EvidenceLevel.MODERATE: 2,
    EvidenceLevel.STRONG: 3,
}

GRADING_CEILING: dict[StudyType, EvidenceLevel] = {
    StudyType.SYSTEMATIC_REVIEW: EvidenceLevel.STRONG,
    StudyType.META_ANALYSIS: EvidenceLevel.STRONG,
    StudyType.RCT: EvidenceLevel.MODERATE,
    StudyType.COHORT: EvidenceLevel.MODERATE,
    StudyType.CROSS_SECTIONAL: EvidenceLevel.LIMITED,
    StudyType.CONSENSUS: EvidenceLevel.MODERATE,
    StudyType.EXPERT_OPINION: EvidenceLevel.EXPERT,
}

STARS: dict[EvidenceLevel, str] = {
    EvidenceLevel.STRONG: "★★★★★",
    EvidenceLevel.MODERATE: "★★★☆☆",
    EvidenceLevel.LIMITED: "★★☆☆☆",
    EvidenceLevel.EXPERT: "★☆☆☆☆",
}


class EvidenceEntry(BaseModel):
    """One graded study in the corpus. Only corpus entries are ever citable."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=80)
    title: str
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1950, le=2100)
    journal: str | None = None
    study_type: StudyType
    population: str | None = None
    conclusions: str
    evidence_level: EvidenceLevel
    doi: str | None = None
    pmid: str | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _enforce_grading_ceiling(self) -> Self:
        ceiling = GRADING_CEILING[self.study_type]
        if _LEVEL_RANK[self.evidence_level] > _LEVEL_RANK[ceiling]:
            msg = (
                f"{self.id}: a {self.study_type.value} study cannot be graded "
                f"{self.evidence_level.value}; its ceiling is {ceiling.value}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _require_locator(self) -> Self:
        if self.doi is None and self.pmid is None:
            msg = f"{self.id}: an entry needs a DOI or a PMID to be citable"
            raise ValueError(msg)
        return self
