"""The session-log carnet contract stays consistent across the skills.

The carnet is a convention (no engine code): program-optimization emits the
fill-in blocks, training-checkin parses the paste-back. These tests guard the
shared format marker and the safety rule against drift between the two.
"""

CARNET_MARKER = "📋 log"
# The multiplication sign is the literal fill-rule token — must match exactly.
FILL_RULE = "poids×reps"  # noqa: RUF001


def _skill(skills, name):
    return next(s for s in skills if s.frontmatter["name"] == name)


def test_optimization_emits_the_carnet(skills):
    body = _skill(skills, "program-optimization").body.casefold()
    assert CARNET_MARKER in body, "optimizer lost the carnet block marker"
    assert "carnet" in body
    assert FILL_RULE in body, "optimizer lost the fill rule"
    assert "douleur" in body
    # The block carries the prescription in brackets (plan + log in one).
    assert "brackets" in body


def test_checkin_ignores_the_prescription_bracket(skills):
    body = _skill(skills, "training-checkin").body.casefold()
    # The printed prescription bracket must not be parsed as logged data.
    assert "parse only what the athlete wrote after" in body


def test_checkin_documents_the_paste_back(skills):
    body = _skill(skills, "training-checkin").body.casefold()
    assert CARNET_MARKER in body, "check-in lost the carnet paste-back path"
    assert FILL_RULE in body
    # Safety: the Douleur line short-circuits the log.
    assert "douleur" in body
    # Never a silent log — confirmation is mandatory.
    assert "confirm in one line" in body


def test_session_day_points_to_the_paste_back(skills):
    body = _skill(skills, "session-day").body.casefold()
    assert CARNET_MARKER in body, "session-day lost the pointer to the carnet"


def test_marker_and_rule_are_shared_not_forked(skills):
    """Emission and parsing must speak the same format — guard against drift."""
    emit = _skill(skills, "program-optimization").body.casefold()
    parse = _skill(skills, "training-checkin").body.casefold()
    for needle in (CARNET_MARKER, FILL_RULE):
        assert needle in emit and needle in parse, (
            f"format token '{needle}' diverged between emission and parsing"
        )
