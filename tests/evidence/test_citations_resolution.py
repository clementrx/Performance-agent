"""Corpus-id resolution for deliverable bibliographies."""

from datetime import date

import pytest

from performance_agent.evidence.citations import resolve_citations
from performance_agent.evidence.corpus import load_corpus
from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Guidance,
    Mesocycle,
    ProgramPlan,
    SessionPlan,
    WeekPlan,
)
from performance_agent.programs.render import plan_citation_ids


def test_resolves_known_ids_with_stars(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    entry = load_corpus()[0]
    resolved = resolve_citations([entry.id])
    citation = resolved[entry.id]
    assert entry.title in citation.citation
    assert "★" in citation.stars


def test_unknown_id_is_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="phantom-id"):
        resolve_citations(["phantom-id"])


def test_plan_citation_ids_orders_and_dedupes():
    def block(cite):
        return ExerciseBlock(
            exercise="Bench press",
            priority="primary",
            sets=3,
            reps="8",
            load_kg=80,
            progression_rule="hold",
            cite=cite,
        )

    plan = ProgramPlan(
        version=1,
        goal_id="g",
        created_on=date(2026, 7, 17),
        advice=[Guidance(text="Creatine.", cite="id-a")],
        rationale=[Guidance(text="Volume.", cite="id-b"), Guidance(text="Judgment.")],
        mesocycles=[
            Mesocycle(
                index=1,
                phase="accumulation",
                weeks=[
                    WeekPlan(
                        week_index=1,
                        volume_factor=1.0,
                        intensity_factor=1.0,
                        sessions=[
                            SessionPlan(
                                id="a",
                                qualities=["strength_heavy"],
                                est_minutes=60,
                                purpose="Upper",
                                blocks=[block("id-c"), block("id-a")],
                                fallbacks=Fallbacks(
                                    low_readiness="halve",
                                    short_on_time="cut",
                                    missing_equipment="dumbbells",
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )
    assert plan_citation_ids(plan) == ["id-a", "id-b", "id-c"]
