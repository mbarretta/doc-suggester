"""Tests for the CLI init subcommand."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from doc_suggester.cli import _run_init, main


# ─── init subcommand ──────────────────────────────────────────────────────────


def test_init_does_not_require_notes(tmp_path: Path) -> None:
    """'init' must not error about missing SE notes."""
    with patch("doc_suggester.cli.asyncio.run", side_effect=lambda coro: coro.close()):
        main(["init", "--project-root", str(tmp_path)])  # no SystemExit(1)


def test_init_calls_run_init(tmp_path: Path) -> None:
    with patch("doc_suggester.cli.asyncio.run", side_effect=lambda coro: coro.close()) as mock_run:
        main(["init", "--project-root", str(tmp_path)])
    mock_run.assert_called_once()


def test_init_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["init", "--help"])
    assert exc_info.value.code == 0


def test_run_init_calls_all_steps(tmp_path: Path) -> None:
    """_run_init must call refresh_blogs, generate_synopses, and refresh_labs."""
    archive = tmp_path / "output" / "unchained-archive.md"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        "## A Post\n\n*Source: https://example.com/a | 2024-01*\n\nContent\n\n---"
    )

    with (
        patch("doc_suggester.blog_manager.refresh_blogs") as mock_blogs,
        patch("doc_suggester.synopsis_generator.generate_synopses", new=AsyncMock(return_value={})) as mock_syn,
        patch("doc_suggester.labs_manager.refresh_labs") as mock_labs,
    ):
        asyncio.run(_run_init(tmp_path))

    mock_blogs.assert_called_once_with(tmp_path, force=True)
    mock_labs.assert_called_once_with(tmp_path, force=True)
    mock_syn.assert_called_once()


def test_run_init_skips_synopses_when_no_posts(tmp_path: Path) -> None:
    """If no posts are found after refresh, synopsis generation is skipped."""
    with (
        patch("doc_suggester.blog_manager.refresh_blogs"),
        patch("doc_suggester.synopsis_generator.generate_synopses", new=AsyncMock()) as mock_syn,
        patch("doc_suggester.labs_manager.refresh_labs"),
    ):
        asyncio.run(_run_init(tmp_path))

    mock_syn.assert_not_called()
