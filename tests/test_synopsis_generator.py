"""Tests for synopsis_generator module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doc_suggester.blog_manager import BlogPost
from doc_suggester.synopsis_generator import generate_synopses, load_synopses


def _make_post(slug: str, title: str = "Test Post") -> BlogPost:
    return BlogPost(
        title=title,
        url=f"https://chainguard.dev/unchained/{slug}",
        date="January 1, 2024",
        excerpt="Some excerpt text.",
        full_content="Full post content here.",
    )


def _make_api_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


# ─── load_synopses ────────────────────────────────────────────────────────────


def test_load_synopses_missing_file(tmp_path: Path):
    result = load_synopses(tmp_path)
    assert result == {}


def test_load_synopses_reads_file(tmp_path: Path):
    (tmp_path / "output").mkdir()
    data = {"java-cves": "CVEs; Java; container security", "slsa": "SLSA; supply chain; provenance"}
    (tmp_path / "output" / "blog-synopses.json").write_text(json.dumps(data))
    result = load_synopses(tmp_path)
    assert result == data


# ─── generate_synopses ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_synopses_no_new_posts(tmp_path: Path):
    """When all post slugs already have synopses, no API calls are made."""
    (tmp_path / "output").mkdir()
    existing = {"java-cves": "CVEs; Java; container images"}
    (tmp_path / "output" / "blog-synopses.json").write_text(json.dumps(existing))
    posts = [_make_post("java-cves")]

    with patch("doc_suggester.synopsis_generator.anthropic.AsyncAnthropic") as mock_cls:
        result = await generate_synopses(tmp_path, posts)

    mock_cls.assert_not_called()
    assert result == existing


@pytest.mark.asyncio
async def test_generate_synopses_generates_missing(tmp_path: Path):
    """Generates synopses for missing posts, saves file, returns full dict."""
    (tmp_path / "output").mkdir()
    existing = {"java-cves": "CVEs; Java; container images"}
    (tmp_path / "output" / "blog-synopses.json").write_text(json.dumps(existing))

    posts = [_make_post("java-cves"), _make_post("slsa", "SLSA Post")]
    new_synopsis = "SLSA; supply chain; provenance; build integrity"

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=_make_api_response(new_synopsis))

    with patch("doc_suggester.synopsis_generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_synopses(tmp_path, posts)

    assert result["java-cves"] == existing["java-cves"]
    assert result["slsa"] == new_synopsis
    mock_client.messages.create.assert_called_once()

    saved = json.loads((tmp_path / "output" / "blog-synopses.json").read_text())
    assert saved["slsa"] == new_synopsis
    assert saved["java-cves"] == existing["java-cves"]


@pytest.mark.asyncio
async def test_generate_synopses_handles_api_failure(tmp_path: Path, caplog):
    """API failure logs a warning, skips that post, saves partial results."""
    (tmp_path / "output").mkdir()
    posts = [
        _make_post("good-post", "Good Post Title"),
        _make_post("bad-post", "Bad Post Title"),
    ]
    good_synopsis = "containers; security; zero CVEs"

    async def _side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        content = messages[0]["content"] if messages else ""
        if "Bad Post Title" in content:
            raise RuntimeError("API error")
        return _make_api_response(good_synopsis)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=_side_effect)

    with (
        patch("doc_suggester.synopsis_generator.anthropic.AsyncAnthropic", return_value=mock_client),
        caplog.at_level("WARNING"),
    ):
        result = await generate_synopses(tmp_path, posts)

    assert result.get("good-post") == good_synopsis
    assert "bad-post" not in result
    assert any("bad-post" in record.message for record in caplog.records)
