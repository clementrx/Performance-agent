"""`performance-agent connect {garmin|strava}` — the one-step wearable setup CLI."""

import subprocess

import pytest

from performance_agent.server import connect
from performance_agent.server.connect import GARMIN_UVX_ARGS, STRAVA_NPX_ARGS, connect_main


class RecordingRunner:
    """Fake subprocess.run capturing commands and returning scripted codes."""

    def __init__(self, returncodes):
        self.returncodes = list(returncodes)
        self.commands = []

    def __call__(self, command, check):
        assert check is False
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncodes.pop(0))


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _tools_present(monkeypatch, *names):
    monkeypatch.setattr(connect.shutil, "which", lambda name: name if name in names else None)


def test_unknown_service_prints_usage_and_exits_2(capsys):
    assert connect_main(["fitbit"]) == 2
    assert "usage: performance-agent connect {garmin|strava}" in capsys.readouterr().err


def test_strava_missing_npx_fails_with_node_pointer(monkeypatch, capsys):
    _tools_present(monkeypatch)
    assert connect_main(["strava"]) == 1
    assert "npx not found" in capsys.readouterr().err


def test_strava_registers_in_claude_and_explains_oauth(monkeypatch, capsys):
    _tools_present(monkeypatch, "npx", "claude")
    runner = RecordingRunner([0])
    assert connect_main(["strava"], run=runner) == 0
    (register,) = runner.commands
    assert register[:6] == ["claude", "mcp", "add", "strava", "-s", "user"]
    assert register[-3:] == list(STRAVA_NPX_ARGS)
    out = capsys.readouterr().out
    assert "strava.com/settings/api" in out
    assert "connect my Strava account" in out


def test_strava_without_claude_cli_prints_manual_snippet(monkeypatch, capsys):
    _tools_present(monkeypatch, "npx")
    runner = RecordingRunner([])
    assert connect_main(["strava"], run=runner) == 0
    assert runner.commands == []
    assert "@r-huijts/strava-mcp-server" in capsys.readouterr().out


def test_missing_uvx_fails_with_install_pointer(monkeypatch, capsys):
    _tools_present(monkeypatch)
    assert connect_main(["garmin"]) == 1
    assert "uvx not found" in capsys.readouterr().err


def test_non_interactive_shell_fails_readably(monkeypatch, capsys):
    _tools_present(monkeypatch, "uvx")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert connect_main(["garmin"]) == 1
    assert "needs a real" in capsys.readouterr().err


@pytest.mark.usefixtures("tty")
def test_failed_login_stops_before_registration(monkeypatch, capsys):
    _tools_present(monkeypatch, "uvx", "claude")
    runner = RecordingRunner([1])
    assert connect_main(["garmin"], run=runner) == 1
    assert len(runner.commands) == 1  # auth only, no claude mcp add
    assert "Garmin login failed" in capsys.readouterr().err


@pytest.mark.usefixtures("tty")
def test_success_authenticates_then_registers_in_claude(monkeypatch, capsys):
    _tools_present(monkeypatch, "uvx", "claude")
    runner = RecordingRunner([0, 0])
    assert connect_main(["garmin"], run=runner) == 0
    auth, register = runner.commands
    assert auth == [*GARMIN_UVX_ARGS, "garmin-mcp-auth"]
    assert register[:6] == ["claude", "mcp", "add", "garmin", "-s", "user"]
    assert register[-1] == "garmin-mcp"
    assert "Restart your agent session" in capsys.readouterr().out


@pytest.mark.usefixtures("tty")
def test_without_claude_cli_prints_manual_snippet(monkeypatch, capsys):
    _tools_present(monkeypatch, "uvx")
    runner = RecordingRunner([0])
    assert connect_main(["garmin"], run=runner) == 0
    assert len(runner.commands) == 1  # auth only
    assert '"garmin"' in capsys.readouterr().out


@pytest.mark.usefixtures("tty")
def test_failed_claude_add_falls_back_to_manual_snippet(monkeypatch, capsys):
    _tools_present(monkeypatch, "uvx", "claude")
    runner = RecordingRunner([0, 1])
    assert connect_main(["garmin"], run=runner) == 0
    assert '"garmin"' in capsys.readouterr().out
