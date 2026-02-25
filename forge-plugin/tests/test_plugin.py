"""Tests for the forge-doc-suggester plugin."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import AsyncMock, patch

from forge_core.context import ExecutionContext
from forge_core.plugin import ResultStatus, ToolPlugin
from forge_doc_suggester.plugin import DocSuggesterPlugin, _DEFAULT_DATA_DIR, create_plugin


def _make_ctx(cancelled: bool = False) -> ExecutionContext:
    event = threading.Event()
    if cancelled:
        event.set()
    return ExecutionContext(
        auth_token="",
        config={},
        on_progress=lambda f, m: None,
        cancel_event=event,
    )


# ─── protocol & metadata ──────────────────────────────────────────────────────


def test_protocol_compliance():
    """Plugin satisfies the ToolPlugin @runtime_checkable protocol."""
    assert isinstance(create_plugin(), ToolPlugin)


def test_requires_auth_is_false():
    assert DocSuggesterPlugin.requires_auth is False


# ─── get_params ───────────────────────────────────────────────────────────────


def test_notes_param_is_required():
    params = {p.name: p for p in DocSuggesterPlugin().get_params()}
    assert params["notes"].required is True


def test_format_has_choices():
    params = {p.name: p for p in DocSuggesterPlugin().get_params()}
    assert params["format"].choices == ["md", "email"]


# ─── run ──────────────────────────────────────────────────────────────────────


def test_run_cancelled_before_start():
    result = DocSuggesterPlugin().run({"notes": "test"}, _make_ctx(cancelled=True))
    assert result.status == ResultStatus.CANCELLED


def test_run_success(capsys):
    with patch("forge_doc_suggester.plugin.suggest", new_callable=AsyncMock) as mock_suggest:
        mock_suggest.return_value = "## Recommendations"
        result = DocSuggesterPlugin().run({"notes": "Java CVEs"}, _make_ctx())
    assert result.status == ResultStatus.SUCCESS
    assert result.data["output"] == "## Recommendations"
    assert "## Recommendations" in capsys.readouterr().out


def test_run_passes_correct_args(tmp_path: Path):
    with patch("forge_doc_suggester.plugin.suggest", new_callable=AsyncMock) as mock_suggest:
        mock_suggest.return_value = "output"
        DocSuggesterPlugin().run(
            {
                "notes": "Java CVEs",
                "format": "email",
                "refresh": True,
                "project_root": tmp_path,
            },
            _make_ctx(),
        )
    mock_suggest.assert_called_once_with(
        se_notes="Java CVEs",
        project_root=tmp_path,
        force_refresh=True,
        output_format="email",
    )


def test_run_project_root_default():
    with patch("forge_doc_suggester.plugin.suggest", new_callable=AsyncMock) as mock_suggest:
        mock_suggest.return_value = "output"
        DocSuggesterPlugin().run({"notes": "test"}, _make_ctx())
    assert mock_suggest.call_args.kwargs["project_root"] == Path(_DEFAULT_DATA_DIR)


def test_run_failure_on_exception():
    with patch("forge_doc_suggester.plugin.suggest", new_callable=AsyncMock) as mock_suggest:
        mock_suggest.side_effect = RuntimeError("API down")
        result = DocSuggesterPlugin().run({"notes": "test"}, _make_ctx())
    assert result.status == ResultStatus.FAILURE
    assert "API down" in result.summary
