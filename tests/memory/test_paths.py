from pathlib import Path

from performance_agent.memory.paths import resolve_athlete_dir


def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path / "custom"))
    assert resolve_athlete_dir() == tmp_path / "custom"


def test_project_local_athlete_dir_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    (tmp_path / "athlete").mkdir()
    monkeypatch.chdir(tmp_path)
    assert resolve_athlete_dir() == tmp_path / "athlete"


def test_falls_back_to_home_dotdir(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(tmp_path)  # no ./athlete here
    assert resolve_athlete_dir() == Path.home() / ".performance-agent"


def test_env_var_expands_user(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", "~/somewhere")
    assert resolve_athlete_dir() == Path.home() / "somewhere"
