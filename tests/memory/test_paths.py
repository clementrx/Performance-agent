from pathlib import Path

import pytest

from performance_agent.memory.paths import resolve_athlete_dir


def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path / "custom"))
    assert resolve_athlete_dir() == tmp_path / "custom"


def test_env_var_expands_user(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", "~/somewhere")
    assert resolve_athlete_dir() == Path.home() / "somewhere"


def test_cwd_is_the_athlete_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    athlete = tmp_path / "marie"
    athlete.mkdir()
    monkeypatch.chdir(athlete)
    assert resolve_athlete_dir() == athlete


def test_refuses_home_as_cwd(monkeypatch):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(Path.home())
    with pytest.raises(ValueError, match="PERFORMANCE_AGENT_HOME"):
        resolve_athlete_dir()


def test_refuses_filesystem_root_as_cwd(monkeypatch):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(Path(Path.cwd().anchor))
    with pytest.raises(ValueError, match="PERFORMANCE_AGENT_HOME"):
        resolve_athlete_dir()


def test_env_var_bypasses_the_guard(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(Path.home()))
    monkeypatch.chdir(Path.home())
    assert resolve_athlete_dir() == Path.home()
