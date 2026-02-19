"""Tests for suggester module (mocked Anthropic + DocsClient)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doc_suggester.blog_manager import BlogPost
from doc_suggester.suggester import _build_blog_index_text, suggest


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


def _make_archive(tmp_path: Path) -> Path:
    """Create a minimal output archive for testing."""
    output = tmp_path / "output"
    output.mkdir()
    archive = output / "unchained-archive.md"
    archive.write_text(
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
    return tmp_path


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


@pytest.mark.asyncio
async def test_suggest_returns_text_response(tmp_path: Path, mock_docs_client):
    """Single-turn response with no tool calls returns final text."""
    _make_archive(tmp_path)

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("## Recommendations\n\n### 1. Java CVE Post")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=final_response)

        result = await suggest("prospect worried about Java CVEs", tmp_path)

    assert "Recommendations" in result
    assert "Java CVE Post" in result


@pytest.mark.asyncio
async def test_suggest_handles_tool_use_loop(tmp_path: Path, mock_docs_client):
    """Multi-turn: Claude calls get_blog_post, then returns text."""
    _make_archive(tmp_path)

    tool_use_block = _make_tool_use_block(
        "tu_1", "get_blog_post", {"url": "https://chainguard.dev/unchained/java-cves"}
    )
    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.content = [tool_use_block]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("## Recommendations\n\n### 1. Java CVE Post\nDetailed content.")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        result = await suggest("prospect worried about Java CVEs", tmp_path)

    assert "Recommendations" in result
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_suggest_triggers_refresh_when_stale(tmp_path: Path, mock_docs_client):
    """When archive is stale, refresh_blogs is called."""
    _make_archive(tmp_path)

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("Recommendations")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=True),
        patch("doc_suggester.suggester.refresh_blogs") as mock_refresh,
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=final_response)

        await suggest("some notes", tmp_path)

    mock_refresh.assert_called_once_with(tmp_path, force=False)


@pytest.mark.asyncio
async def test_suggest_force_refresh_calls_refresh(tmp_path: Path, mock_docs_client):
    """force_refresh=True triggers refresh even when archive is fresh."""
    _make_archive(tmp_path)

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("Recommendations")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.refresh_blogs") as mock_refresh,
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=final_response)

        await suggest("some notes", tmp_path, force_refresh=True)

    mock_refresh.assert_called_once_with(tmp_path, force=True)


@pytest.mark.asyncio
async def test_suggest_get_security_docs_tool(tmp_path: Path, mock_docs_client):
    """Claude can call get_security_docs tool."""
    _make_archive(tmp_path)

    tool_use_block = _make_tool_use_block("tu_sec", "get_security_docs", {})
    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.content = [tool_use_block]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("Security recommendations")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        result = await suggest("prospect using Cosign", tmp_path)

    mock_docs_client.get_security_docs.assert_called_once()
    assert "Security recommendations" in result


@pytest.mark.asyncio
async def test_suggest_unknown_blog_url_returns_not_found(tmp_path: Path, mock_docs_client):
    """Requesting a URL not in the archive returns a not-found message."""
    _make_archive(tmp_path)

    tool_use_block = _make_tool_use_block(
        "tu_missing", "get_blog_post", {"url": "https://chainguard.dev/unchained/nonexistent"}
    )
    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.content = [tool_use_block]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [_make_text_block("Fallback recommendations")]

    with (
        patch("doc_suggester.suggester.is_archive_stale", return_value=False),
        patch("doc_suggester.suggester.DocsClient", return_value=mock_docs_client),
        patch("doc_suggester.suggester.anthropic.AsyncAnthropic") as mock_anthropic,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        result = await suggest("some notes", tmp_path)

    # Verify the tool result message contained the "not found" text.
    # Index [2] because the second call's messages list is [user, asst(tool_use), user(tool_results)].
    # We can't use [-1] — mock captures a reference, and the final assistant message gets appended
    # to the same list object after the second call completes.
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_message = second_call_messages[2]
    assert tool_result_message["role"] == "user"
    content = tool_result_message["content"]
    assert any("not found" in item.get("content", "") for item in content)
