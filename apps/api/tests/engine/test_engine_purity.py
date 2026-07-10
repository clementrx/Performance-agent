"""Architectural test: the engine must stay pure (stdlib-only, no I/O)."""

import ast
from pathlib import Path

import performance_agent.engine

assert performance_agent.engine.__file__ is not None  # a real package on disk
ENGINE_DIR = Path(performance_agent.engine.__file__).parent

ALLOWED_STDLIB = {
    "math",
    "dataclasses",
    "enum",
    "typing",
    "collections",
    "collections.abc",
}
ALLOWED_INTERNAL_PREFIX = "performance_agent.engine"


def iter_imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        # Bare relative imports (`from . import x`) have module=None and are
        # invisible here; ruff's TID ban-relative-imports covers them repo-wide.
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def test_engine_modules_import_only_stdlib_math_and_engine_siblings():
    violations = []
    for path in sorted(ENGINE_DIR.rglob("*.py")):
        for module in iter_imported_modules(path):
            allowed = module in ALLOWED_STDLIB or module.startswith(ALLOWED_INTERNAL_PREFIX)
            if not allowed:
                violations.append(f"{path.name} imports {module}")
    assert not violations, (
        "engine/ must stay deterministic and dependency-free (spec section 4.2); "
        f"forbidden imports found: {violations}"
    )
