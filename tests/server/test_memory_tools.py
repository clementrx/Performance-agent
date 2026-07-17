"""In-process tests for the memory MCP tools (isolated athlete dir per test)."""

from pathlib import Path

import pytest

from tests.exercises.test_dataset import write_fixture_dataset
from tests.program_plans import plan_dict


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    # Keep tests hermetic: never pick up a real exercises-dataset clone.
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(tmp_path / "no-dataset"))
    return tmp_path


@pytest.mark.anyio
async def test_read_athlete_on_fresh_directory(client):
    result = await client.call_tool("read_athlete", {})
    assert not result.isError
    snapshot = result.structuredContent
    assert snapshot["profile"]["locale"] == "en"
    assert snapshot["goals"] == []
    assert snapshot["program_version"] is None
    assert snapshot["analysis_version"] is None
    assert snapshot["dossier_version"] is None
    assert snapshot["nutrition_frame_version"] is None


@pytest.mark.anyio
async def test_read_athlete_reports_pipeline_versions(client):
    await client.call_tool(
        "save_analysis",
        {"markdown_body": "# Needs analysis", "goal_id": "bench-120"},
    )
    result = await client.call_tool("read_athlete", {})
    snapshot = result.structuredContent
    assert snapshot["analysis_version"] == 1
    assert snapshot["dossier_version"] is None


@pytest.mark.anyio
async def test_write_profile_then_read_back(client, athlete_home):
    result = await client.call_tool(
        "write_profile",
        {"profile": {"locale": "fr", "sport": "running", "training_age": "intermediate"}},
    )
    assert not result.isError
    assert (athlete_home / "profile.yaml").exists()

    back = await client.call_tool("read_athlete", {})
    assert back.structuredContent["profile"]["locale"] == "fr"
    assert back.structuredContent["profile"]["training_age"] == "intermediate"


@pytest.mark.anyio
async def test_invalid_profile_is_rejected_readably(client):
    result = await client.call_tool("write_profile", {"profile": {"locale": "de"}})
    assert result.isError
    text = result.content[0].text
    assert "en" in text and "fr" in text and "es" in text


@pytest.mark.anyio
async def test_goal_lifecycle(client):
    added = await client.call_tool(
        "upsert_goal",
        {
            "goal": {
                "id": "sub-45-10k",
                "statement": "10K under 45:00",
                "deadline": "2026-10-30",
            }
        },
    )
    assert not added.isError
    assert added.structuredContent["total_goals"] == 1

    snapshot = await client.call_tool("read_athlete", {})
    assert snapshot.structuredContent["goals"][0]["id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_log_session_and_checkin(client):
    logged = await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-08T18:00:00", "rpe": 7, "duration_min": 60}},
    )
    assert not logged.isError
    assert logged.structuredContent["total_sessions"] == 1

    first = await client.call_tool("log_checkin", {"entry": {"at": "2026-06-26T09:00:00"}})
    assert not first.isError
    second = await client.call_tool("log_checkin", {"entry": {"at": "2026-07-10T09:00:00"}})
    assert second.structuredContent["days_since_last"] == 14


@pytest.mark.anyio
async def test_logged_sessions_can_be_read_back(client):
    await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-01T18:00:00", "rpe": 7, "duration_min": 60}},
    )
    await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-03T18:00:00", "rpe": 5, "duration_min": 45}},
    )
    result = await client.call_tool("read_sessions", {})
    assert not result.isError
    sessions = result.structuredContent["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["rpe"] == 7

    limited = await client.call_tool("read_sessions", {"last_n": 1})
    assert len(limited.structuredContent["sessions"]) == 1
    assert limited.structuredContent["sessions"][0]["rpe"] == 5


@pytest.mark.anyio
async def test_logged_checkins_can_be_read_back(client):
    await client.call_tool("log_checkin", {"entry": {"at": "2026-06-26T09:00:00"}})
    await client.call_tool("log_checkin", {"entry": {"at": "2026-07-10T09:00:00", "fatigue": 6}})
    result = await client.call_tool("read_checkins", {})
    assert not result.isError
    checkins = result.structuredContent["checkins"]
    assert len(checkins) == 2
    assert checkins[-1]["fatigue"] == 6


@pytest.mark.anyio
async def test_backdated_checkin_negative_delta_through_tool(client):
    await client.call_tool("log_checkin", {"entry": {"at": "2026-07-10T09:00:00"}})
    stored = await client.call_tool("log_checkin", {"entry": {"at": "2026-07-05T09:00:00"}})
    assert stored.structuredContent["days_since_last"] == -5


@pytest.mark.anyio
async def test_write_profile_is_a_full_replace(client):
    await client.call_tool("write_profile", {"profile": {"locale": "fr", "equipment": ["barbell"]}})
    await client.call_tool("write_profile", {"profile": {"locale": "fr"}})
    back = await client.call_tool("read_athlete", {})
    assert back.structuredContent["profile"]["equipment"] == []  # dropped: replace, not merge


@pytest.mark.anyio
async def test_program_versioning_through_tools(client):
    v1 = await client.call_tool("save_program", {"plan": plan_dict(goal_id="sub-45-10k")})
    assert not v1.isError
    assert v1.structuredContent["version"] == 1

    rejected = await client.call_tool("save_program", {"plan": plan_dict(goal_id="sub-45-10k")})
    assert rejected.isError
    assert "reason" in rejected.content[0].text

    v2 = await client.call_tool(
        "save_program",
        {"plan": plan_dict(goal_id="sub-45-10k"), "reason": "plateau at week 4"},
    )
    assert v2.structuredContent["version"] == 2

    latest = await client.call_tool("read_program", {})
    assert latest.structuredContent["version"] == 2
    assert latest.structuredContent["reason"] == "plateau at week 4"
    first_version = await client.call_tool("read_program", {"version": 1})
    assert "# Program v1 — sub-45-10k" in first_version.structuredContent["markdown"]
    assert first_version.structuredContent["plan"]["goal_id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_save_program_writes_session_html_without_dataset(client):
    saved = await client.call_tool("save_program", {"plan": plan_dict(goal_id="sub-45-10k")})
    html_path = saved.structuredContent["html_path"]
    assert html_path is not None
    page = Path(html_path).read_text(encoding="utf-8")
    assert html_path.endswith("program-v1.html")
    assert "Back Squat" in page and "4x5" in page
    assert "data:image/gif" not in page  # no dataset clone -> prescription only


@pytest.mark.anyio
async def test_save_program_html_embeds_media_in_profile_locale(client, monkeypatch, tmp_path):
    dataset_dir = write_fixture_dataset(tmp_path / "dataset")
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(dataset_dir))
    await client.call_tool("write_profile", {"profile": {"locale": "fr"}})
    plan = plan_dict(goal_id="squat-160")
    plan["mesocycles"][0]["weeks"][0]["sessions"][0]["blocks"][0]["exercise_id"] = "back-squat"

    saved = await client.call_tool("save_program", {"plan": plan})
    page = Path(saved.structuredContent["html_path"]).read_text(encoding="utf-8")
    assert page.count("data:image/gif;base64,") == 1
    assert "Barre sur le dos." in page
    assert "Semaine 1" in page


@pytest.mark.anyio
async def test_read_program_before_any_save_is_a_readable_error(client):
    result = await client.call_tool("read_program", {})
    assert result.isError
    assert "save_program" in result.content[0].text


@pytest.mark.anyio
async def test_get_time_context_quotes_deltas(client):
    await client.call_tool("log_session", {"entry": {"performed_at": "2026-07-01T18:00:00"}})
    await client.call_tool(
        "upsert_goal",
        {
            "goal": {
                "id": "sub-45-10k",
                "statement": "10K under 45:00",
                "deadline": "2026-10-30",
            }
        },
    )
    result = await client.call_tool("get_time_context", {})
    assert not result.isError
    context = result.structuredContent
    assert context["last_session_on"] == "2026-07-01"
    assert isinstance(context["days_since_last_session"], int)
    assert context["goals"][0]["goal_id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_last_n_must_be_positive(client):
    result = await client.call_tool("read_sessions", {"last_n": 0})
    assert result.isError
    result = await client.call_tool("read_checkins", {"last_n": -2})
    assert result.isError


@pytest.mark.anyio
async def test_memory_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {
        "read_athlete",
        "write_profile",
        "upsert_goal",
        "log_session",
        "log_checkin",
        "log_readiness",
        "read_readiness",
        "save_program",
        "read_program",
        "get_time_context",
        "save_analysis",
        "read_analysis",
        "save_research_dossier",
        "read_research_dossier",
        "save_nutrition_frame",
        "read_nutrition_frame",
        "read_calendar",
        "upsert_calendar_event",
        "remove_calendar_event",
        "set_recurring_constraints",
        "build_season_plan",
    } <= names


@pytest.mark.anyio
async def test_calendar_and_season_plan_through_tools(client):
    await client.call_tool(
        "upsert_calendar_event",
        {
            "event": {
                "id": "race-a",
                "date": "2026-11-02",
                "kind": "competition",
                "priority": "A",
                "label": "Marathon",
            }
        },
    )
    await client.call_tool(
        "set_recurring_constraints",
        {"recurring": [{"weekday": 2, "kind": "club_practice", "label": "club run"}]},
    )
    calendar = await client.call_tool("read_calendar", {})
    assert len(calendar.structuredContent["events"]) == 1
    assert len(calendar.structuredContent["recurring"]) == 1

    plan = await client.call_tool("build_season_plan", {"modality": "endurance"})
    assert not plan.isError
    phases = [s["phase_type"] for s in plan.structuredContent["segments"]]
    assert "taper" in phases and phases[-1] == "competition"
    assert plan.structuredContent["macro_emphases"] is None  # standalone season

    with_macro = await client.call_tool(
        "build_season_plan",
        {"modality": "endurance", "year_emphases": {"aerobic_capacity": 0.7, "speed": 0.3}},
    )
    assert not with_macro.isError
    assert with_macro.structuredContent["macro_emphases"]["aerobic_capacity"] == pytest.approx(0.7)


@pytest.mark.anyio
async def test_remove_calendar_event_through_tools(client):
    await client.call_tool(
        "upsert_calendar_event",
        {
            "event": {
                "id": "race",
                "date": "2026-11-02",
                "kind": "competition",
                "priority": "A",
                "label": "M",
            }
        },
    )
    removed = await client.call_tool("remove_calendar_event", {"event_id": "race"})
    assert removed.structuredContent["total_events"] == 0


@pytest.mark.anyio
async def test_analysis_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_analysis", {"markdown_body": "# Needs analysis", "goal_id": "squat-160"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "analysis" / "needs-analysis-v1.md").exists()

    read_back = await client.call_tool("read_analysis", {})
    assert read_back.structuredContent["goal_id"] == "squat-160"
    assert read_back.structuredContent["body"] == "# Needs analysis"

    unreasoned = await client.call_tool(
        "save_analysis", {"markdown_body": "v2", "goal_id": "squat-160"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_research_dossier_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_research_dossier", {"markdown_body": "# Dossier", "goal_id": "squat-160"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "research" / "dossier-v1.md").exists()

    read_back = await client.call_tool("read_research_dossier", {})
    assert read_back.structuredContent["body"] == "# Dossier"

    unreasoned = await client.call_tool(
        "save_research_dossier", {"markdown_body": "v2", "goal_id": "squat-160"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_nutrition_frame_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "# Frame", "goal_id": "cut-15pct"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "nutrition" / "frame-v1.md").exists()

    read_back = await client.call_tool("read_nutrition_frame", {})
    assert read_back.structuredContent["goal_id"] == "cut-15pct"
    assert read_back.structuredContent["body"] == "# Frame"

    unreasoned = await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "v2", "goal_id": "cut-15pct"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_read_athlete_reports_nutrition_frame_version(client):
    await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "# Frame", "goal_id": "cut-15pct"}
    )
    result = await client.call_tool("read_athlete", {})
    assert result.structuredContent["nutrition_frame_version"] == 1


@pytest.mark.anyio
async def test_reading_unsaved_documents_errors_readably(client):
    analysis = await client.call_tool("read_analysis", {})
    assert analysis.isError
    assert "save_analysis" in analysis.content[0].text
    dossier = await client.call_tool("read_research_dossier", {})
    assert dossier.isError
    assert "save_research_dossier" in dossier.content[0].text
    frame = await client.call_tool("read_nutrition_frame", {})
    assert frame.isError
    assert "save_nutrition_frame" in frame.content[0].text


@pytest.mark.anyio
async def test_log_session_round_trips_structured_exercises(client):
    entry = {
        "performed_at": "2026-07-11T18:00:00",
        "kind": "strength",
        "exercises": [
            {
                "name": "back squat",
                "sets": [
                    {"reps": 5, "load_kg": 100.0, "rir": 2},
                    {"reps": 5, "load_kg": 100.0, "rir": 1},
                ],
            }
        ],
    }
    result = await client.call_tool("log_session", {"entry": entry})
    assert not result.isError

    read_back = await client.call_tool("read_sessions", {})
    sessions = read_back.structuredContent["sessions"]
    assert sessions[0]["exercises"][0]["sets"][1]["rir"] == 1


@pytest.mark.anyio
async def test_log_session_returns_empty_flags_for_clean_entry(client):
    result = await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-08T18:00:00", "rpe": 7, "duration_min": 60}},
    )
    assert not result.isError
    assert result.structuredContent["flags"] == []
    assert result.structuredContent["total_sessions"] == 1


@pytest.mark.anyio
async def test_log_session_flags_an_implausible_e1rm_jump(client):
    baseline = {
        "performed_at": "2026-07-01T18:00:00",
        "exercises": [{"name": "back squat", "sets": [{"reps": 3, "load_kg": 100.0}]}],
    }
    await client.call_tool("log_session", {"entry": baseline})
    spike = {
        "performed_at": "2026-07-08T18:00:00",
        "exercises": [{"name": "back squat", "sets": [{"reps": 3, "load_kg": 150.0}]}],
    }
    result = await client.call_tool("log_session", {"entry": spike})
    assert not result.isError
    codes = [f["code"] for f in result.structuredContent["flags"]]
    assert "e1rm_jump" in codes
    # the entry is still logged despite the flag
    assert result.structuredContent["total_sessions"] == 2


@pytest.mark.anyio
async def test_log_session_external_source_is_stored(client):
    entry = {
        "performed_at": "2026-07-08T20:00:00",
        "kind": "club practice",
        "source": "external",
        "avg_hr": 150.0,
        "rpe": 6,
        "duration_min": 90,
    }
    await client.call_tool("log_session", {"entry": entry})
    read_back = await client.call_tool("read_sessions", {})
    assert read_back.structuredContent["sessions"][0]["source"] == "external"


@pytest.mark.anyio
async def test_log_and_read_readiness(client):
    logged = await client.call_tool(
        "log_readiness",
        {
            "entry": {
                "at": "2026-07-12T07:00:00",
                "sleep": 2,
                "fatigue": 3,
                "soreness": 2,
                "stress": 2,
            }
        },
    )
    assert not logged.isError
    assert logged.structuredContent["total_readiness"] == 1

    read_back = await client.call_tool("read_readiness", {})
    assert not read_back.isError
    reads = read_back.structuredContent["readiness"]
    assert len(reads) == 1
    assert reads[0]["sleep"] == 2


@pytest.mark.anyio
async def test_read_readiness_empty_on_fresh_dir(client):
    result = await client.call_tool("read_readiness", {})
    assert not result.isError
    assert result.structuredContent["readiness"] == []
