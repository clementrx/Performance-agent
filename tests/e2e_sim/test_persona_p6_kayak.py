"""Persona P6 — kayak sprint (NO seed model).

Proves the machine is SEED-INDEPENDENT: a hand-authored, research-filled kayak
PerformanceModel (mixed prior/judgment provenance) flows through the whole Phase 0-8
pipeline exactly like a seeded sport — model -> gaps -> test battery -> scored
selection -> program -> specificity/residual checks -> per-quality rates -> macro.
No code path special-cases the sport string. No LLM; deterministic.
"""

from datetime import date, timedelta

from performance_agent.memory import store
from performance_agent.memory.exercise_library import (
    check_program_specificity,
    score_library_exercises,
)
from performance_agent.memory.macro import build_macro_plan, check_program_residuals
from performance_agent.memory.performance_models import (
    compute_performance_gaps,
    plan_performance_test_battery,
)
from performance_agent.memory.response import _per_quality_rates
from performance_agent.memory.schemas import (
    Benchmark,
    CalendarEvent,
    EnergySystemSplit,
    ExerciseBlock,
    Fallbacks,
    InjuryRiskEntry,
    KpiResult,
    KpiSpec,
    Mesocycle,
    PerformanceModel,
    ProgramPlan,
    Provenance,
    QualityRequirement,
    SessionPlan,
    WeekPlan,
)

TODAY = date(2026, 7, 13)


def _kayak_model() -> PerformanceModel:
    """A research-filled K1 200 m model: mixed prior/judgment provenance."""
    return PerformanceModel(
        discipline="canoe sprint",
        event="K1 200 m",
        qualities=[
            QualityRequirement(
                quality="anaerobic_capacity",
                weight=0.35,
                provenance=Provenance(kind="prior"),
                rationale="200 m is glycolytically dominant.",
            ),
            QualityRequirement(
                quality="max_strength",
                weight=0.2,
                provenance=Provenance(kind="judgment"),
                rationale="Pull force off the catch.",
            ),
            QualityRequirement(
                quality="muscular_endurance",
                weight=0.2,
                provenance=Provenance(kind="judgment"),
                rationale="Stroke rate maintenance.",
            ),
            QualityRequirement(
                quality="explosive_strength",
                weight=0.15,
                provenance=Provenance(kind="judgment"),
                rationale="Start acceleration.",
            ),
            QualityRequirement(
                quality="aerobic_capacity",
                weight=0.1,
                provenance=Provenance(kind="prior"),
                rationale="Recovery base.",
            ),
        ],
        kpis=[
            KpiSpec(
                id="k1-200-time",
                name="K1 200 m time",
                quality="anaerobic_capacity",
                protocol="on-water 200 m time trial",
                unit="s",
                higher_is_better=False,
                benchmarks=[
                    Benchmark(level="competitive", value=40.0, provenance=Provenance(kind="prior")),
                    Benchmark(level="elite", value=34.0, provenance=Provenance(kind="prior")),
                ],
            ),
            KpiSpec(
                id="bench-pull-1rm",
                name="Bench pull 1RM",
                quality="max_strength",
                protocol="prone bench pull 1RM",
                test_protocol="one_rm_test",
                unit="kg",
                higher_is_better=True,
                benchmarks=[
                    Benchmark(level="elite", value=110.0, provenance=Provenance(kind="judgment"))
                ],
            ),
        ],
        injury_risks=[
            InjuryRiskEntry(
                region="shoulder",
                mechanism="repetitive high-rate pulling",
                screen="scapular control and pain-free range",
                provenance=Provenance(kind="judgment"),
            )
        ],
        energy_systems=EnergySystemSplit(
            aerobic=0.25,
            anaerobic_lactic=0.6,
            anaerobic_alactic=0.15,
            provenance=Provenance(kind="prior"),
        ),
        sources=[],
    )


def _seed_kayak(base_dir):
    store.save_performance_model(base_dir, _kayak_model())
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="worlds", date=date(2028, 8, 1), kind="competition", priority="A", label="Worlds"
        ),
    )
    store.append_kpi_result(
        base_dir,
        KpiResult(date=date(2026, 7, 1), kpi_id="k1-200-time", protocol="tt", value=38.0, unit="s"),
    )
    store.append_kpi_result(
        base_dir,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="bench-pull-1rm", protocol="1rm", value=95.0, unit="kg"
        ),
    )


def test_kayak_model_saves_and_reads(tmp_path):
    _seed_kayak(tmp_path)
    stored = store.read_performance_model(tmp_path)
    assert stored is not None
    assert stored.event == "K1 200 m"
    # Provenance labels survive the round-trip (mixed prior/judgment).
    kinds = {q.provenance.kind for q in stored.qualities}
    assert kinds == {"prior", "judgment"}


def test_kayak_gaps_and_battery(tmp_path):
    _seed_kayak(tmp_path)
    gaps = compute_performance_gaps(tmp_path, "elite", TODAY)
    measured = {g["kpi_id"] for g in gaps["kpi_gaps"] if g["status"] == "measured"}
    assert {"k1-200-time", "bench-pull-1rm"} <= measured
    battery = plan_performance_test_battery(tmp_path, TODAY)
    assert battery["tests"]


def test_kayak_scored_selection(tmp_path):
    _seed_kayak(tmp_path)
    scored = score_library_exercises(
        tmp_path,
        {"max_strength": 1.0},
        "specific_prep",
        pattern="pull_h",
        available_equipment=["barbell", "cable", "machine", "dumbbell", "bench"],
    )
    assert scored
    assert scored[0]["excluded_reason"] is None


def _kayak_program() -> ProgramPlan:
    def _session(week_index, eid, quality):
        return SessionPlan(
            id=f"w{week_index:02d}-s1",
            weekday=0,
            qualities=[quality],
            est_minutes=60,
            purpose="kayak-specific development",
            blocks=[
                ExerciseBlock(
                    exercise=eid,
                    exercise_id=eid,
                    priority="primary",
                    sets=4,
                    reps="6",
                    rest_s=150,
                    progression_rule="double progression",
                )
            ],
            fallbacks=Fallbacks(low_readiness="a", short_on_time="b", missing_equipment="c"),
        )

    weeks = [
        WeekPlan(
            week_index=1,
            volume_factor=1.0,
            intensity_factor=1.0,
            sessions=[_session(1, "barbell-row", "club_practice")],
        ),
        WeekPlan(
            week_index=10,
            volume_factor=1.0,
            intensity_factor=1.0,
            sessions=[_session(10, "row-erg", "endurance_long")],
        ),
    ]
    return ProgramPlan(
        version=1,
        goal_id="kayak",
        created_on=date(2026, 7, 12),
        mesocycles=[Mesocycle(index=1, phase="general_prep", weeks=weeks)],
    )


def test_kayak_program_checks_run(tmp_path):
    _seed_kayak(tmp_path)
    store.save_program(tmp_path, _kayak_program())
    # Both structural checks run on an unseeded sport with no special-casing.
    specificity = check_program_specificity(tmp_path)
    residuals = check_program_residuals(tmp_path)
    assert isinstance(specificity, list)
    assert isinstance(residuals, list)


def test_kayak_macro_and_quality_rates(tmp_path):
    _seed_kayak(tmp_path)
    plan = build_macro_plan(tmp_path, horizon_years=3)
    assert [y.year_type for y in plan.years] == ["development", "qualification", "realization"]
    # Per-quality rates key off the hand-authored model's KPIs, no seed needed.
    for week in range(6):
        store.append_kpi_result(
            tmp_path,
            KpiResult(
                date=date(2026, 1, 1) + timedelta(days=week * 7),
                kpi_id="bench-pull-1rm",
                protocol="1rm",
                value=90.0 + week,
                unit="kg",
            ),
        )
    rates = _per_quality_rates(tmp_path)
    assert any(r.kpi_id == "bench-pull-1rm" for r in rates)
