"""Documentation folder: registry, scan states, mark validation."""

from datetime import date

import pytest

from performance_agent.memory.documents import (
    DOCUMENTATION_DIR,
    README_FILE,
    REGISTRY_FILE,
    ensure_documentation_dir,
    load_registry,
    mark_processed,
    scan_documents,
)

TODAY = date(2026, 7, 17)


def _drop(base, name, content=b"pdf-bytes"):
    doc_dir = base / DOCUMENTATION_DIR
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / name).write_bytes(content)


def test_ensure_creates_folder_and_readme(tmp_path):
    path = ensure_documentation_dir(tmp_path)
    assert path == tmp_path / DOCUMENTATION_DIR
    assert path.is_dir()
    readme = path / README_FILE
    assert readme.exists()
    assert "documentation" in readme.read_text(encoding="utf-8").casefold()


def test_ensure_is_idempotent_and_keeps_readme_edits(tmp_path):
    readme = ensure_documentation_dir(tmp_path) / README_FILE
    readme.write_text("custom", encoding="utf-8")
    ensure_documentation_dir(tmp_path)
    assert readme.read_text(encoding="utf-8") == "custom"


def test_scan_reports_new_files_and_excludes_registry_and_readme(tmp_path):
    ensure_documentation_dir(tmp_path)
    _drop(tmp_path, "study.pdf")
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["new"]] == ["study.pdf"]
    assert result["modified"] == []
    assert result["processed"] == []
    assert result["removed"] == []
    assert result["unreadable"] == []


def test_mark_then_scan_reports_processed_with_summary(tmp_path):
    _drop(tmp_path, "study.pdf")
    record = mark_processed(
        tmp_path,
        "study.pdf",
        lane="evidence",
        summary="Creatine meta-analysis.",
        evidence_ids=["creatine-2017"],
        known_evidence_ids={"creatine-2017"},
        today=TODAY,
    )
    assert record.lane == "evidence"
    result = scan_documents(tmp_path)
    assert result["new"] == []
    assert result["processed"][0]["summary"] == "Creatine meta-analysis."


def test_modified_file_is_reported_for_reprocessing(tmp_path):
    _drop(tmp_path, "study.pdf")
    mark_processed(
        tmp_path,
        "study.pdf",
        lane="context",
        summary="v1",
        known_evidence_ids=set(),
        today=TODAY,
    )
    _drop(tmp_path, "study.pdf", content=b"changed-bytes")
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["modified"]] == ["study.pdf"]


def test_removed_is_derived_not_stored(tmp_path):
    _drop(tmp_path, "study.pdf")
    mark_processed(
        tmp_path,
        "study.pdf",
        lane="context",
        summary="s",
        known_evidence_ids=set(),
        today=TODAY,
    )
    (tmp_path / DOCUMENTATION_DIR / "study.pdf").unlink()
    result = scan_documents(tmp_path)
    assert result["removed"] == ["study.pdf"]
    stored = load_registry(tmp_path)
    assert [r.filename for r in stored.documents] == ["study.pdf"]


def test_unreadable_lane_needs_no_summary(tmp_path):
    _drop(tmp_path, "corrupt.pdf")
    record = mark_processed(
        tmp_path,
        "corrupt.pdf",
        lane="unreadable",
        known_evidence_ids=set(),
        today=TODAY,
    )
    assert record.summary is None
    assert scan_documents(tmp_path)["unreadable"][0]["filename"] == "corrupt.pdf"


def test_mark_unknown_file_fails(tmp_path):
    ensure_documentation_dir(tmp_path)
    with pytest.raises(ValueError, match=r"ghost\.pdf"):
        mark_processed(
            tmp_path,
            "ghost.pdf",
            lane="context",
            summary="s",
            known_evidence_ids=set(),
            today=TODAY,
        )


def test_mark_evidence_or_context_requires_summary(tmp_path):
    _drop(tmp_path, "study.pdf")
    with pytest.raises(ValueError, match="summary"):
        mark_processed(
            tmp_path,
            "study.pdf",
            lane="evidence",
            known_evidence_ids=set(),
            today=TODAY,
        )


def test_mark_rejects_unknown_evidence_id(tmp_path):
    _drop(tmp_path, "study.pdf")
    with pytest.raises(ValueError, match="phantom-id"):
        mark_processed(
            tmp_path,
            "study.pdf",
            lane="evidence",
            summary="s",
            evidence_ids=["phantom-id"],
            known_evidence_ids={"other"},
            today=TODAY,
        )


def test_corrupt_registry_is_rebuilt_empty(tmp_path):
    _drop(tmp_path, "study.pdf")
    (tmp_path / DOCUMENTATION_DIR / REGISTRY_FILE).write_text("not: [valid", encoding="utf-8")
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["new"]] == ["study.pdf"]
