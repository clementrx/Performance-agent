"""Structural invariants every coaching skill must satisfy."""

EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "needs-analysis",
    "program-planning",
    "program-optimization",
    "nutrition-planning",
    "program-review",
    "training-checkin",
    "program-adaptation",
    "program-report",
    "deep-research",
    "session-day",
}


def test_all_expected_skills_exist(skills):
    assert {s.frontmatter["name"] for s in skills} == EXPECTED_SKILLS


def test_every_skill_has_wellformed_frontmatter(skills):
    for skill in skills:
        assert skill.frontmatter.get("name"), f"{skill.path}: missing name"
        description = skill.frontmatter.get("description", "")
        assert len(description) >= 30, f"{skill.path}: description too thin"
        assert isinstance(skill.frontmatter.get("tools"), list), (
            f"{skill.path}: must declare a tools: list (may be empty)"
        )


def test_directory_name_matches_frontmatter_name(skills):
    for skill in skills:
        assert skill.path.parent.name == skill.frontmatter["name"], skill.path


def test_coach_skill_carries_the_global_rules(skills):
    coach = next(s for s in skills if s.frontmatter["name"] == "performance-coach")
    body = coach.body.casefold()
    for needle in (
        "read_athlete",
        "get_time_context",
        "check_citations",
        "not medical advice",
        "locale",
        "never compute dates",
        "needs-analysis",
        "deep-research",
        "program-planning",
        "program-optimization",
        "nutrition-planning",
        "program-review",
    ):
        assert needle in body, f"coach skill lost the rule: {needle}"


def test_onboarding_skill_protocol(skills):
    onboarding = next(s for s in skills if s.frontmatter["name"] == "athlete-onboarding")
    body = onboarding.body.casefold()
    for needle in (
        "write_profile",
        "upsert_goal",
        "one question",
        "equipment",
        "injur",
        "lift_inventory",
        "estimate_1rm",
        "calendar_type",
        "body_fat_pct",
        "bodyweight_kg",
        "split_preferences",
    ):
        assert needle in body, f"onboarding skill lost: {needle}"


def test_needs_analysis_skill_protocol(skills):
    analysis = next(s for s in skills if s.frontmatter["name"] == "needs-analysis")
    body = analysis.body.casefold()
    for needle in (
        "assess_endurance_goal",
        "assess_strength_goal",
        "assess_hypertrophy_goal",
        "assess_bodycomp_goal",
        "estimate_1rm",
        "drivers",
        "counter-proposal",
        "honest",
        "save_analysis",
        "research questions",
    ):
        assert needle in body, f"needs-analysis skill lost: {needle}"


def test_planning_skill_protocol(skills):
    planning = next(s for s in skills if s.frontmatter["name"] == "program-planning")
    body = planning.body.casefold()
    for needle in (
        "read_analysis",
        "read_research_dossier",
        "calendar_type",
        "build_block_cycle",
        "build_periodization_waves",
        "build_undulating_sessions",
        "build_inseason_maintenance",
        "build_peaking_block",
        "weekly_set_targets_for",
        "skeleton",
        "coaching judgment",
        "check_citations",
        "nutrition-planning",
        "program-optimization",
        "submaximal",
        "intensity mode",
        "needs-analysis",
    ):
        assert needle in body, f"program-planning skill lost: {needle}"


def test_optimization_skill_protocol(skills):
    optimization = next(s for s in skills if s.frontmatter["name"] == "program-optimization")
    body = optimization.body.casefold()
    for needle in (
        "skeleton",
        "prescribe_reps_load",
        "prescribe_load",
        "estimate_1rm",
        "progress_double_progression",
        "prescribe_top_set_backoff",
        "prescribe_wave_loading",
        "convert_rpe_to_rir",
        "predict_race_time",
        "read_nutrition_frame",
        "save_program",
        "check_citations",
        "split_preferences",
        "rest",
        "purpose",
        "stars",
        "program-review",
        "approved",
        "returned",
    ):
        assert needle in body, f"program-optimization skill lost: {needle}"


def test_checkin_skill_protocol(skills):
    checkin = next(s for s in skills if s.frontmatter["name"] == "training-checkin")
    body = checkin.body.casefold()
    for needle in (
        "get_time_context",
        "log_checkin",
        "log_session",
        "pain",
        "adherence",
        "fatigue",
        "vigile",
        "stall",
        "failed reps",
        "read_sessions",
        "read_checkins",
        "read_nutrition_frame",
        "bodyweight_kg",
        "weekly_change_kg",
        "drift",
        "recurring_fixtures",
        "refer out",
        "stop prescribing",
    ):
        assert needle in body, f"checkin skill lost: {needle}"


def test_adaptation_skill_protocol(skills):
    adaptation = next(s for s in skills if s.frontmatter["name"] == "program-adaptation")
    body = adaptation.body.casefold()
    for needle in (
        "read_sessions",
        "read_checkins",
        "compute_acwr",
        "compute_weekly_loads",
        "save_program",
        "reason",
        "confirm",
        "program-review",
        "approved",
        "vigile",
        "under-recovery",
        "under-stimulus",
        "weekly_set_targets_for",
        "rir",
    ):
        assert needle in body, f"adaptation skill lost: {needle}"


def test_report_skill_protocol(skills):
    report = next(s for s in skills if s.frontmatter["name"] == "program-report")
    body = report.body.casefold()
    for needle in ("render_report", "check_citations", "coach", "expert", "mode"):
        assert needle in body, f"report skill lost: {needle}"


def test_research_skill_protocol(skills):
    research = next(s for s in skills if s.frontmatter["name"] == "deep-research")
    body = research.body.casefold()
    for needle in (
        "read_analysis",
        "search_evidence_live",
        "save_evidence",
        "save_research_dossier",
        "facet",
        "coverage",
        "canonical",
        "contradiction",
        "thin evidence",
        "failed",
    ):
        assert needle in body, f"deep-research skill lost: {needle}"


def test_review_skill_protocol(skills):
    review = next(s for s in skills if s.frontmatter["name"] == "program-review")
    body = review.body.casefold()
    for needle in (
        "compliance",
        "adversarial",
        "check_citations",
        "get_citation",
        "prescribe_load",
        "prescribe_reps_load",
        "weekly_set_targets_for",
        "compute_session_load",
        "read_nutrition_frame",
        "read_research_dossier",
        "exceeds_safe_rate",
        "subagent",
        "approved",
        "returned",
        "never saves",
        "verbatim",
        "program-planning",
        "program-optimization",
    ):
        assert needle in body, f"program-review skill lost: {needle}"


def test_nutrition_skill_protocol(skills):
    nutrition = next(s for s in skills if s.frontmatter["name"] == "nutrition-planning")
    body = nutrition.body.casefold()
    for needle in (
        "compute_bmr_tdee",
        "prescribe_nutrition_targets",
        "save_nutrition_frame",
        "clamped_to_floor",
        "protein",
        "activity factor",
        "not medical advice",
        "refer out",
        "stop prescribing",
        "review_trigger",
        "intensification",
    ):
        assert needle in body, f"nutrition-planning skill lost: {needle}"


def test_session_day_skill_protocol(skills):
    session_day = next(s for s in skills if s.frontmatter["name"] == "session-day")
    body = session_day.body.casefold()
    for needle in (
        "read_program",
        "compute_readiness",
        "adjust_session",
        "compress_session",
        "substitute_exercise",
        "log_session_adjustment",
        "read_session_adjustments",
        "escalat",
        "program-adaptation",
        "never",
        "hooper",
    ):
        assert needle in body, f"session-day skill lost: {needle}"
