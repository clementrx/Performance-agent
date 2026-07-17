"""Athlete-dropped documents: folder bootstrap, registry, scan, mark.

The athlete drops files (studies, physio reports, past programs) into
documentation/; the agent detects new/changed files by content hash and records
what it did with each one. Only `processed` and `unreadable` are stored —
`new`, `modified` and `removed` are derived at scan time. The registry is
reconstructible by design: a deleted or corrupt index.yaml simply makes files
show up as new again (corpus entries are verified independently and survive).
"""

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Literal, Self, TypedDict

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DOCUMENTATION_DIR = "documentation"
REGISTRY_FILE = "index.yaml"
README_FILE = "README.md"
_EXCLUDED_FILES = {REGISTRY_FILE, README_FILE}

_README_CONTENT = """\
# Documentation

EN — Drop documents for your coach here: published studies (PDF), physio or
medical reports you want considered, lab test results, past training programs.
New and changed files are picked up automatically. A study whose DOI/PMID can
be verified joins the evidence corpus; everything else informs your coaching
as context but is never presented as science.

FR — Déposez ici les documents pour votre coach : études publiées (PDF),
bilans kiné/médicaux à partager, résultats de tests, anciens programmes.
Les fichiers nouveaux ou modifiés sont détectés automatiquement. Une étude
dont le DOI/PMID est vérifiable rejoint le corpus scientifique ; tout le
reste nourrit le coaching comme contexte, jamais présenté comme de la science.
"""

Lane = Literal["evidence", "context", "unreadable"]


class DocumentRecord(BaseModel):
    """One processed (or unreadable) dropped file, keyed by filename."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    first_seen: date
    processed_on: date
    lane: Lane
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _summary_required_unless_unreadable(self) -> Self:
        if self.lane != "unreadable" and not self.summary:
            msg = f"{self.filename}: a summary is required for lane {self.lane!r}"
            raise ValueError(msg)
        return self


class DocumentRegistry(BaseModel):
    """The whole documentation/index.yaml file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    documents: list[DocumentRecord] = Field(default_factory=list)


class DocumentView(TypedDict):
    """A file awaiting processing (new or modified)."""

    filename: str
    path: str
    size_bytes: int


class ProcessedView(TypedDict):
    """A file the agent already handled, with what it retained."""

    filename: str
    path: str
    lane: str
    summary: str | None


class ScanResult(TypedDict):
    """Derived folder state: only processed/unreadable are stored on disk."""

    path: str
    new: list[DocumentView]
    modified: list[DocumentView]
    processed: list[ProcessedView]
    removed: list[str]
    unreadable: list[ProcessedView]


def documentation_dir(base_dir: Path) -> Path:
    """Return the documentation folder path (never creates it)."""
    return base_dir / DOCUMENTATION_DIR


def ensure_documentation_dir(base_dir: Path) -> Path:
    """Create the folder and its README when missing; never overwrites."""
    doc_dir = documentation_dir(base_dir)
    doc_dir.mkdir(parents=True, exist_ok=True)
    readme = doc_dir / README_FILE
    if not readme.exists():
        readme.write_text(_README_CONTENT, encoding="utf-8")
    return doc_dir


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry(base_dir: Path) -> DocumentRegistry:
    """Load the registry; a missing or corrupt file yields an empty registry."""
    path = documentation_dir(base_dir) / REGISTRY_FILE
    if not path.exists():
        return DocumentRegistry()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return DocumentRegistry.model_validate(raw or {})
    except (yaml.YAMLError, ValidationError):
        return DocumentRegistry()


def _save_registry(base_dir: Path, registry: DocumentRegistry) -> None:
    path = documentation_dir(base_dir) / REGISTRY_FILE
    _atomic_write(
        path,
        yaml.safe_dump(registry.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
    )


def scan_documents(base_dir: Path) -> ScanResult:
    """Compare the folder against the registry; derives new/modified/removed."""
    doc_dir = ensure_documentation_dir(base_dir)
    registry = load_registry(base_dir)
    records = {record.filename: record for record in registry.documents}
    present = {
        path.name: path
        for path in sorted(doc_dir.iterdir())
        if path.is_file() and path.name not in _EXCLUDED_FILES
    }
    result = ScanResult(
        path=str(doc_dir), new=[], modified=[], processed=[], removed=[], unreadable=[]
    )
    for name, path in present.items():
        view = DocumentView(filename=name, path=str(path), size_bytes=path.stat().st_size)
        record = records.get(name)
        if record is None:
            result["new"].append(view)
        elif record.sha256 != _sha256(path):
            result["modified"].append(view)
        else:
            processed = ProcessedView(
                filename=name, path=str(path), lane=record.lane, summary=record.summary
            )
            if record.lane == "unreadable":
                result["unreadable"].append(processed)
            else:
                result["processed"].append(processed)
    result["removed"] = sorted(set(records) - set(present))
    return result


def mark_processed(  # noqa: PLR0913 -- one keyword per registry field, all named
    base_dir: Path,
    filename: str,
    *,
    lane: Lane,
    summary: str | None = None,
    key_points: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    known_evidence_ids: set[str],
    today: date | None = None,
) -> DocumentRecord:
    """Record the outcome for one file; replaces any previous record.

    known_evidence_ids must cover the whole corpus (packaged + personal); the
    caller builds it so this module never depends on the evidence package.
    """
    path = documentation_dir(base_dir) / filename
    if not path.is_file():
        msg = f"{filename}: no such file in {documentation_dir(base_dir)}"
        raise ValueError(msg)
    unknown = [eid for eid in (evidence_ids or []) if eid not in known_evidence_ids]
    if unknown:
        msg = f"{filename}: evidence_ids not in the corpus: {unknown}"
        raise ValueError(msg)
    registry = load_registry(base_dir)
    previous = {record.filename: record for record in registry.documents}
    current = today or date.today()
    record = DocumentRecord(
        filename=filename,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        first_seen=previous[filename].first_seen if filename in previous else current,
        processed_on=current,
        lane=lane,
        summary=summary,
        key_points=key_points or [],
        evidence_ids=evidence_ids or [],
    )
    kept = [r for r in registry.documents if r.filename != filename]
    _save_registry(base_dir, DocumentRegistry(documents=[*kept, record]))
    return record
