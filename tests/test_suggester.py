"""Tests for suggester module (mocked Anthropic + DocsClient)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doc_suggester.blog_manager import BlogPost
from doc_suggester.labs_manager import LabEntry
from doc_suggester.suggester import _build_blog_index_text, suggest


# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_archive(tmp_path: Path) -> None:
    """Create a minimal output archive for testing."""
    output = tmp_path / "output"
    output.mkdir()
    (output / "unchained-archive.md").write_text(
        "# Archive\n\n---\n\n"
        "## Java CVE Post\n\n"
        "*Source: https://chainguard.dev/unchained/java-cves | March 1, 2024*\n\n"
        "Java images with zero CVEs.\n\n---\n"
    )
    checkpoint = {
        "java-cves": {
            "title": "Java CVE Post",
            "url": "https://chainguard.dev/unchained/java-cves",
            "date": "March 1, 2024",
            "scraped_at": "2024-03-01T00:00:00Z",
        }
    }
    (output / "checkpoint.json").write_text(json.dumps(checkpoint))


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id: str, name: str, input_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _make_end_response(text: str = "Recommendations") -> MagicMock:
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [_make_text_block(text)]
    return response


def _make_tool_response(block: MagicMock) -> MagicMock:
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


@pytest.fixture
def mock_docs_client():
    """Provide a pre-configured async mock DocsClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_security_docs = AsyncMock(return_value="Security docs content")
    client.get_image_docs = AsyncMock(return_value="Image docs content")
    client.get_tool_docs = AsyncMock(return_value="Tool docs content")
    client.search = AsyncMock(return_value="Search results")
    return client


@pytest.fixture
def suggest_env(tmp_path: Path, mock_docs_client):
    """Archive + patched dependencies. Yields (project_root, mock_client, mock_refresh)."""
    _make_archive(tmp_path)
    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.refresh_blogs") as mock_refresh,
        patch("doc_suggester.suggester.is_labs_stale", return_value=False),
        patch("doc_suggester.suggester.refresh_labs"),
        patch("doc_suggester.suggester.load_labs", return_value=[]),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        yield tmp_path, mock_client, mock_refresh


# ─── _build_blog_index_text ──────────────────────────────────────────────────


def test_build_blog_index_text_empty():
    text = _build_blog_index_text([])
    assert "Blog Index" in text


def test_build_blog_index_text_includes_posts():
    posts = [
        BlogPost(
            title="Zero CVEs in Java",
            url="https://chainguard.dev/unchained/zero-cve-java",
            date="March 15, 2024",
            excerpt="Chainguard Java images...",
            full_content="Full content here",
        ),
        BlogPost(
            title="SLSA Compliance",
            url="https://chainguard.dev/unchained/slsa",
            date="January 8, 2024",
            excerpt="SLSA provides...",
            full_content="Full SLSA content",
        ),
    ]
    text = _build_blog_index_text(posts)
    assert "Zero CVEs in Java" in text
    assert "https://chainguard.dev/unchained/zero-cve-java" in text
    assert "March 15, 2024" in text
    assert "SLSA Compliance" in text


def test_build_blog_index_text_no_date():
    posts = [
        BlogPost(
            title="Undated Post",
            url="https://chainguard.dev/unchained/undated",
            date="",
            excerpt="Some content",
            full_content="Full content",
        )
    ]
    text = _build_blog_index_text(posts)
    assert "Undated Post" in text
    # No empty " | " date separator
    assert " | \n" not in text


# ─── suggest ─────────────────────────────────────────────────────────────────


async def test_suggest_returns_text_response(suggest_env):
    """Single-turn response with no tool calls returns final text."""
    tmp_path, mock_client, _ = suggest_env
    mock_client.messages.create = AsyncMock(
        return_value=_make_end_response("## Recommendations\n\n### 1. Java CVE Post")
    )
    result = await suggest("prospect worried about Java CVEs", tmp_path)
    assert "Recommendations" in result
    assert "Java CVE Post" in result


async def test_suggest_handles_tool_use_loop(suggest_env):
    """Multi-turn: Claude calls get_blog_post, then returns text."""
    tmp_path, mock_client, _ = suggest_env
    tool_use_block = _make_tool_use_block(
        "tu_1", "get_blog_post", {"url": "https://chainguard.dev/unchained/java-cves"}
    )
    mock_client.messages.create = AsyncMock(side_effect=[
        _make_tool_response(tool_use_block),
        _make_end_response("## Recommendations\n\n### 1. Java CVE Post\nDetailed content."),
    ])
    result = await suggest("prospect worried about Java CVEs", tmp_path)
    assert "Recommendations" in result
    assert mock_client.messages.create.call_count == 2


async def test_suggest_triggers_refresh_when_stale(suggest_env):
    """When archive is stale, refresh_blogs is called."""
    tmp_path, mock_client, mock_refresh = suggest_env
    mock_client.messages.create = AsyncMock(return_value=_make_end_response("Recommendations"))
    with patch("doc_suggester.suggester.is_archive_stale", return_value=True):
        await suggest("some notes", tmp_path)
    mock_refresh.assert_called_once_with(tmp_path, force=False)


async def test_suggest_force_refresh_calls_refresh(suggest_env):
    """force_refresh=True triggers refresh even when archive is fresh."""
    tmp_path, mock_client, mock_refresh = suggest_env
    mock_client.messages.create = AsyncMock(return_value=_make_end_response("Recommendations"))
    await suggest("some notes", tmp_path, force_refresh=True)
    mock_refresh.assert_called_once_with(tmp_path, force=True)


async def test_suggest_get_security_docs_tool(suggest_env, mock_docs_client):
    """Claude can call get_security_docs tool."""
    tmp_path, mock_client, _ = suggest_env
    tool_use_block = _make_tool_use_block("tu_sec", "get_security_docs", {})
    mock_client.messages.create = AsyncMock(side_effect=[
        _make_tool_response(tool_use_block),
        _make_end_response("Security recommendations"),
    ])
    result = await suggest("prospect using Cosign", tmp_path)
    mock_docs_client.get_security_docs.assert_called_once()
    assert "Security recommendations" in result


async def test_suggest_unknown_blog_url_returns_not_found(suggest_env):
    """Requesting a URL not in the archive returns a not-found message."""
    tmp_path, mock_client, _ = suggest_env
    tool_use_block = _make_tool_use_block(
        "tu_missing", "get_blog_post", {"url": "https://chainguard.dev/unchained/nonexistent"}
    )
    mock_client.messages.create = AsyncMock(side_effect=[
        _make_tool_response(tool_use_block),
        _make_end_response("Fallback recommendations"),
    ])
    await suggest("some notes", tmp_path)
    # Verify the tool result message contained the "not found" text.
    # Index [2] because the second call's messages list is [user, asst(tool_use), user(tool_results)].
    # We can't use [-1] — mock captures a reference, and the final assistant message gets appended
    # to the same list object after the second call completes.
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_message = second_call_messages[2]
    assert tool_result_message["role"] == "user"
    content = tool_result_message["content"]
    assert any("not found" in item.get("content", "") for item in content)


async def test_suggest_get_lab_tool(tmp_path: Path, mock_docs_client):
    """Claude can call get_lab tool and receives formatted lab details."""
    sample_lab = LabEntry(
        id="ll202509",
        title="Java Zero-CVE Lab",
        date="2025-09",
        url="https://edu.chainguard.dev/software-security/learning-labs/ll202509/",
        recording_url="https://www.youtube.com/watch?v=abc123",
        technologies=["Java", "Docker"],
        difficulty="beginner",
        intent_signals=["Java CVEs", "container security"],
        summary="Reduce CVEs in Java container images.",
    )
    _make_archive(tmp_path)
    tool_use_block = _make_tool_use_block("tu_lab", "get_lab", {"lab_id": "ll202509"})
    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.refresh_blogs"),
        patch("doc_suggester.suggester.is_labs_stale", return_value=False),
        patch("doc_suggester.suggester.refresh_labs"),
        patch("doc_suggester.suggester.load_labs", return_value=[sample_lab]),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[
            _make_tool_response(tool_use_block),
            _make_end_response("Java lab recommended"),
        ])
        result = await suggest("Java developer worried about CVEs", tmp_path)

    assert "Java lab recommended" in result
    # Verify the tool result sent back to Claude contains lab details
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_message = second_call_messages[2]
    content = tool_result_message["content"]
    assert any("Java Zero-CVE Lab" in item.get("content", "") for item in content)
