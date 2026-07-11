"""Structural invariants every coaching skill must satisfy."""

EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "needs-analysis",
    "program-generation",
    "training-checkin",
    "program-adaptation",
    "program-report",
    "deep-research",
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


def test_generation_skill_protocol(skills):
    generation = next(s for s in skills if s.frontmatter["name"] == "program-generation")
    body = generation.body.casefold()
    for needle in (
        "search_evidence",
        "build_periodization_waves",
        "prescribe_load",
        "save_program",
        "check_citations",
        "stars",
        "purpose",
    ):
        assert needle in body, f"generation skill lost: {needle}"


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
