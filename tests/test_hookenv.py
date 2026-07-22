"""Tests for the pre-push hook launcher.

``scripts/hookenv.py`` decides which interpreter the pre-push hooks run
under. The Windows and POSIX venv layouts differ, and only one of them can
be exercised on any given machine, so both are covered here by pointing the
candidate list at real files under ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import hookenv


class TestResolveInterpreter:
    """Interpreter selection, per layout."""

    @pytest.mark.parametrize("layout", [("Scripts", "python.exe"), ("bin", "python")])
    def test_prefers_repo_venv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: tuple[str, str]
    ) -> None:
        """A venv interpreter that exists on disk is chosen over sys.executable."""
        subdir, name = layout
        venv_python = tmp_path / ".venv" / subdir / name
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()
        monkeypatch.setattr(hookenv, "_VENV_CANDIDATES", (venv_python,))

        interpreter, source = hookenv.resolve_interpreter()

        assert interpreter == venv_python
        assert source == "repo .venv"

    def test_falls_back_when_no_venv_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no venv on disk, the running interpreter is used and labelled as such.

        The label matters: it is the difference between a hook that states
        which interpreter produced its green bar and one that leaves it to
        be assumed.
        """
        monkeypatch.setattr(hookenv, "_VENV_CANDIDATES", (Path("does-not-exist"),))

        interpreter, source = hookenv.resolve_interpreter()

        assert interpreter.exists()
        assert source == "current interpreter (no .venv found)"


class TestMain:
    """Argument handling and the not-importable guard."""

    def test_no_tool_given_exits_nonzero(self) -> None:
        """An empty argument list is a usage error, not a silent success."""
        assert hookenv.main([]) == 1

    def test_unimportable_tool_fails_loudly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A tool missing from the resolved interpreter fails instead of falling back to PATH."""
        rc = hookenv.main(["definitely_not_an_installed_module_xyz"])

        assert rc == 1
        assert "not importable" in capsys.readouterr().err

    def test_runs_tool_and_returns_its_exit_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A real tool runs under the resolved interpreter and its exit code propagates."""
        rc = hookenv.main(["ruff", "--version"])

        assert rc == 0
        assert "hookenv: ruff via" in capsys.readouterr().err

    def test_missing_venv_advises_creating_one_not_installing_into_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With no venv, the advice names the real remedy.

        Under ``language: python`` the fallback interpreter is pre-commit's
        own managed environment, which will never hold this project's tools.
        Telling the reader to install into it sends them to a dead end; the
        remedy is to create ``.venv`` at the repository root.
        """
        monkeypatch.setattr(hookenv, "_VENV_CANDIDATES", (Path("does-not-exist"),))

        rc = hookenv.main(["definitely_not_an_installed_module_xyz"])
        err = capsys.readouterr().err

        assert rc == 1
        assert "no project virtualenv found at" in err
        assert "python -m venv .venv" in err

    def test_present_venv_missing_tool_advises_installing_into_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With a venv present but the tool absent, the advice is to install into that venv.

        Positive control for the test above: the two branches must give
        different advice, or the message is not actually conditional.
        """
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")  # not a real interpreter; the probe fails, which is the point
        monkeypatch.setattr(hookenv, "_VENV_CANDIDATES", (venv_python,))

        rc = hookenv.main(["ruff"])
        err = capsys.readouterr().err

        assert rc == 1
        assert 'install the development dependencies there: pip install -e ".[dev]"' in err
        assert "no project virtualenv found" not in err
