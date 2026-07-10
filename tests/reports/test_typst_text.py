from performance_agent.reports.typst_text import escape_typst, markdown_to_typst


def test_escape_neutralizes_typst_syntax():
    hostile = r'#import "x" $math$ *bold* _em_ @ref [link] <tag> `code` \back'
    escaped = escape_typst(hostile)
    for char in "#$*_@[]<>`":
        assert f"\\{char}" in escaped
    assert "\\\\back" in escaped


def test_escape_leaves_plain_text_alone():
    assert escape_typst("Squat 5x5 at 80% — allez !") == "Squat 5x5 at 80% — allez !"


def test_headings_convert():
    md = "# Title\n## Week 1\n### Tuesday"
    assert markdown_to_typst(md) == "= Title\n== Week 1\n=== Tuesday"


def test_bullets_and_paragraphs_survive():
    md = "- easy run 45 min\n- strides\n\nRest well."
    out = markdown_to_typst(md)
    assert "- easy run 45 min" in out
    assert "Rest well." in out


def test_bold_converts():
    assert markdown_to_typst("**purpose**: economy") == "*purpose*: economy"


def test_content_inside_structures_is_escaped():
    md = "# Week #3 [taper]\n- load @ 80% *of* 1RM"
    out = markdown_to_typst(md)
    assert out.startswith("= Week \\#3 \\[taper\\]")
    assert "\\@ 80% \\*of\\*" in out


def test_hostile_injection_cannot_escape_into_code():
    md = 'Try this: #eval("1+1") and $x^2$'
    out = markdown_to_typst(md)
    # "#eval" not in out is impossible to also require alongside the escaped
    # form below: "\#eval" (backslash-prefix escaping) necessarily contains
    # "#eval" as a substring. The escaped form is the actual security property.
    assert "\\#eval" in out
    assert "\\$x\\^2\\$" in out or "\\$" in out


def test_comment_syntax_is_neutralized():
    out = escape_typst("see https://strava.com/act /* hidden */")
    assert "//" not in out.replace("\\/\\/", "")  # no live // remains
    assert "\\/\\*" in out


def test_urls_survive_as_visible_text():
    assert "strava" in markdown_to_typst("check https://strava.com/x")


def test_embedded_newlines_cannot_break_line_structure():
    out = escape_typst("line1\n= fake heading")
    assert "\n" not in out
    assert out == "line1 \\= fake heading"


def test_body_lines_cannot_become_headings_or_lists():
    out = markdown_to_typst("= 5x5 back squat\n+ do it daily")
    assert out.startswith("\\=")
    assert "\\+" in out


def test_odd_bold_markers_do_not_bleed():
    out = markdown_to_typst("**bold** then 10**2 unclosed")
    assert out.count("*") % 2 == 0 or "\\*\\*" in out  # no dangling live emphasis
    assert "*bold*" in out


def test_double_asterisk_exponent_is_literal():
    out = markdown_to_typst("power: 10**2")
    assert "*" not in out.replace("\\*", "")  # nothing live
