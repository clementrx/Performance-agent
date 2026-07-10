"""Structural invariants every coaching skill must satisfy."""

EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "goal-assessment",
    "program-generation",
    "training-checkin",
    "program-adaptation",
}


def test_all_expected_skills_exist(skills):
    assert {s.frontmatter["name"] for s in skills} >= {"performance-coach"}


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
    for needle in ("write_profile", "upsert_goal", "one question", "equipment", "injur"):
        assert needle in body, f"onboarding skill lost: {needle}"


def test_assessment_skill_protocol(skills):
    assessment = next(s for s in skills if s.frontmatter["name"] == "goal-assessment")
    body = assessment.body.casefold()
    for needle in (
        "assess_endurance_goal",
        "drivers",
        "counter-proposal",
        "honest",
        "estimate_1rm",
    ):
        assert needle in body, f"assessment skill lost: {needle}"
