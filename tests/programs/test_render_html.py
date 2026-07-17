import pytest

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.exercises.dataset import ExerciseMediaIndex
from performance_agent.memory.schemas import ExerciseBlock, Guidance, SessionPlan, WeekPlan
from performance_agent.programs.render_html import render_program_html
from tests.exercises.test_dataset import write_fixture_dataset
from tests.program_plans import a_fallbacks, minimal_plan


@pytest.fixture
def index(tmp_path):
    return ExerciseMediaIndex.load(write_fixture_dataset(tmp_path / "ds"))


def squat_block(**overrides) -> ExerciseBlock:
    fields = {
        "exercise": "Back Squat",
        "exercise_id": "back-squat",
        "priority": "primary",
        "sets": 4,
        "reps": "5",
        "load_kg": 120.0,
        "rest_s": 180,
        "progression_rule": "double_progression(5-5, +2.5kg)",
    }
    fields.update(overrides)
    return ExerciseBlock.model_validate(fields)


def linked_plan(**overrides):
    session = SessionPlan(
        id="w01-s1-lower-heavy",
        weekday=0,
        qualities=["strength_heavy"],
        patterns=["squat"],
        est_minutes=75,
        purpose="Build the squat base",
        blocks=[squat_block()],
        fallbacks=a_fallbacks(),
    )
    week = WeekPlan(week_index=1, volume_factor=1.0, intensity_factor=0.9, sessions=[session])
    return minimal_plan(
        mesocycles=[{"index": 1, "phase": "accumulation", "weeks": [week.model_dump()]}],
        **overrides,
    )


def test_prescription_without_media_index():
    page = render_program_html(minimal_plan())
    assert page.startswith("<!doctype html>")
    assert "Program v1 — 20260712 — squat-160" in page
    assert "Back Squat" in page
    assert "4x5" in page and "120 kg" in page and "180s" in page
    assert "double_progression(5-5, +2.5kg)" in page
    assert "top set at RPE 7, skip block C" in page
    assert "MEDIA" not in page
    assert "gymvisual.com" not in page


def test_media_embedded_once_and_credited(index):
    page = render_program_html(linked_plan(), index=index)
    assert page.count("data:image/gif;base64,") == 1
    assert '<div class="media m-0043"></div>' in page
    assert '.m-0043{background-image:url("data:image/gif;base64,' in page
    assert "gymvisual.com" in page
    assert "Stand with the bar on your back." in page


def test_media_renders_without_javascript(index):
    # Phone viewers (iOS Quick Look, in-app previews) don't run scripts: the
    # GIFs must be pure HTML+CSS, so the page may not contain any <script>.
    page = render_program_html(linked_plan(), index=index)
    assert "<script" not in page


def test_no_external_resources(index):
    page = render_program_html(linked_plan(), index=index)
    for needle in ('src="http', 'href="http://', "url(http", "url(//", "@import", "fetch("):
        credit_free = page.replace('href="https://gymvisual.com/"', "").replace(
            'href="https://github.com/hasaneyldrm/exercises-dataset"', ""
        )
        assert needle not in credit_free


def test_french_locale_labels_and_steps(index):
    page = render_program_html(linked_plan(), locale="fr", index=index)
    assert "Semaine 1" in page
    assert "Lundi" in page
    assert "repos 180s" in page
    assert "Barre sur le dos." in page
    assert 'lang="fr"' in page
    assert "Échauffement" in page


def test_warmup_ramp_rendered_for_primary_heavy_block(index):
    page = render_program_html(linked_plan(), index=index)
    assert "x5" in page  # ramp reps from engine warmup_scheme
    assert "kg)" in page


def test_unmatched_exercise_renders_without_media(index):
    page = render_program_html(minimal_plan(), index=index)
    # fixture plan blocks carry no exercise_id and no dataset name matches
    assert "Back Squat" in page
    assert "data:image/gif" not in page


def test_html_escapes_user_text():
    page = render_program_html(minimal_plan(note="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


_CITATIONS = {
    "id-a": ResolvedCitation(
        citation="Kreider et al. (2017). ISSN position stand. DOI: 10.1186/s12970-017-0173-z.",
        stars="★★★★★",
        doi="10.1186/s12970-017-0173-z",
        pmid=None,
    )
}


def _guidance_plan():
    session = SessionPlan(
        id="w01-s1-lower-heavy",
        weekday=0,
        qualities=["strength_heavy"],
        est_minutes=75,
        purpose="Build the squat base",
        blocks=[squat_block(cite="id-a")],
        fallbacks=a_fallbacks(),
    )
    week = WeekPlan(week_index=1, volume_factor=1.0, intensity_factor=0.9, sessions=[session])
    return minimal_plan(
        mesocycles=[{"index": 1, "phase": "accumulation", "weeks": [week.model_dump()]}],
        advice=[Guidance(text="Creatine 5 g/day.", cite="id-a")],
        rationale=[Guidance(text="12-16 hard sets per muscle per week.")],
    )


def _bare_plan():
    return minimal_plan()


def test_html_renders_banner_markers_and_bibliography():
    page = render_program_html(_guidance_plan(), locale="en", citations=_CITATIONS)
    assert "Advice" in page and "Creatine 5 g/day." in page
    assert "[1]" in page  # marker on the advice line and the citing block
    assert "Sources" in page and "★★★★★" in page
    assert "https://doi.org/10.1186/s12970-017-0173-z" in page


def test_html_without_guidance_or_citations_is_unchanged_shape():
    page = render_program_html(_bare_plan(), locale="en")
    assert "Sources" not in page and "Advice" not in page


def test_html_localizes_banner_titles_in_french():
    page = render_program_html(_guidance_plan(), locale="fr", citations=_CITATIONS)
    assert "Conseils" in page and "Pourquoi ce programme" in page
