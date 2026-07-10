"""Shared fixtures: skill discovery and parsing."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@dataclass(frozen=True)
class Skill:
    """A parsed SKILL.md: frontmatter mapping + markdown body."""

    name: str
    path: Path
    frontmatter: dict
    body: str


def parse_skill(path: Path) -> Skill:
    """Parse a SKILL.md file (--- frontmatter --- body)."""
    text = path.read_text(encoding="utf-8")
    if text.count("---\n") < 2:
        msg = f"{path} is missing YAML frontmatter delimited by '---' lines"
        raise ValueError(msg)
    _, frontmatter_text, body = text.split("---\n", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        msg = f"{path} frontmatter must be a YAML mapping"
        raise ValueError(msg)
    return Skill(
        name=str(frontmatter.get("name", path.parent.name)),
        path=path,
        frontmatter=frontmatter,
        body=body,
    )


def discover_skills() -> list[Skill]:
    """Parse every skills/<name>/SKILL.md in the repo."""
    return [parse_skill(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))]


@pytest.fixture(scope="session")
def skills() -> list[Skill]:
    return discover_skills()
