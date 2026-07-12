"""Shared fixtures for activity-import tests."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    """Directory holding the hand-authored activity-file fixtures."""
    return FIXTURES
