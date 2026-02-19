"""Tests for blog_manager module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from doc_suggester.blog_manager import (
    BlogPost,
    _parse_date,
    get_most_recent_blog_date,
    is_archive_stale,
    parse_blog_index,
)


# ─── _parse_date ─────────────────────────────────────────────────────────────


def test_parse_date_full_month_name():
    result = _parse_date("January 5, 2024")
    assert result == datetime(2024, 1, 5, tzinfo=timezone.utc)


def test_parse_date_padded_day():
    result = _parse_date("March 15, 2023")
    assert result == datetime(2023, 3, 15, tzinfo=timezone.utc)


def test_parse_date_iso_format():
    result = _parse_date("2024-06-01")
    assert result == datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_parse_date_invalid():
    assert _parse_date("not a date") is None
    assert _parse_date("") is None


# ─── get_most_recent_blog_date ────────────────────────────────────────────────


def test_get_most_recent_blog_date_no_checkpoint(tmp_path: Path):
    assert get_most_recent_blog_date(tmp_path) is None


def test_get_most_recent_blog_date_empty_checkpoint(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "checkpoint.json").write_text("{}")
    assert get_most_recent_blog_date(tmp_path) is None


def test_get_most_recent_blog_date_returns_latest(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    checkpoint = {
        "post-a": {"title": "A", "url": "https://example.com/a", "date": "January 5, 2024", "scraped_at": ""},
        "post-b": {"title": "B", "url": "https://example.com/b", "date": "March 20, 2024", "scraped_at": ""},
        "post-c": {"title": "C", "url": "https://example.com/c", "date": "February 10, 2024", "scraped_at": ""},
    }
    (output / "checkpoint.json").write_text(json.dumps(checkpoint))
    result = get_most_recent_blog_date(tmp_path)
    assert result == datetime(2024, 3, 20, tzinfo=timezone.utc)


def test_get_most_recent_blog_date_skips_missing_dates(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    checkpoint = {
        "post-a": {"title": "A", "url": "https://example.com/a", "date": "", "scraped_at": ""},
        "post-b": {"title": "B", "url": "https://example.com/b", "date": "June 1, 2023", "scraped_at": ""},
    }
    (output / "checkpoint.json").write_text(json.dumps(checkpoint))
    result = get_most_recent_blog_date(tmp_path)
    assert result == datetime(2023, 6, 1, tzinfo=timezone.utc)


# ─── is_archive_stale ────────────────────────────────────────────────────────


def test_is_archive_stale_no_archive(tmp_path: Path):
    assert is_archive_stale(tmp_path) is True


def test_is_archive_stale_no_checkpoint(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "unchained-archive.md").write_text("# archive")
    assert is_archive_stale(tmp_path) is True


def test_is_archive_stale_recent(tmp_path: Path):
    from datetime import timedelta
    output = tmp_path / "output"
    output.mkdir()
    (output / "unchained-archive.md").write_text("# archive")
    recent_date = datetime.now(timezone.utc) - timedelta(days=2)
    checkpoint = {
        "post-a": {
            "title": "A",
            "url": "https://example.com/a",
            "date": recent_date.strftime("%B %-d, %Y"),
            "scraped_at": "",
        }
    }
    (output / "checkpoint.json").write_text(json.dumps(checkpoint))
    assert is_archive_stale(tmp_path) is False


def test_is_archive_stale_old(tmp_path: Path):
    from datetime import timedelta
    output = tmp_path / "output"
    output.mkdir()
    (output / "unchained-archive.md").write_text("# archive")
    old_date = datetime.now(timezone.utc) - timedelta(days=30)
    checkpoint = {
        "post-a": {
            "title": "A",
            "url": "https://example.com/a",
            "date": old_date.strftime("%B %-d, %Y"),
            "scraped_at": "",
        }
    }
    (output / "checkpoint.json").write_text(json.dumps(checkpoint))
    assert is_archive_stale(tmp_path) is True


# ─── parse_blog_index ────────────────────────────────────────────────────────


_SAMPLE_ARCHIVE = """\
# Unchained Blog Archive

*Articles from [chainguard.dev/unchained](https://chainguard.dev/unchained)*

---

## Zero CVEs in Production Java

*Source: https://chainguard.dev/unchained/zero-cve-java | March 15, 2024*

Chainguard's Java images ship with zero known CVEs at time of publication.
We achieve this by building from scratch using Wolfi.

---

## Supply Chain Security with SLSA

*Source: https://chainguard.dev/unchained/slsa-supply-chain | January 8, 2024*

SLSA (Supply-chain Levels for Software Artifacts) provides a framework...

---

## No-date post

*Source: https://chainguard.dev/unchained/no-date-post*

Content without a date.

---
"""


def test_parse_blog_index_returns_posts(tmp_path: Path):
    archive = tmp_path / "unchained-archive.md"
    archive.write_text(_SAMPLE_ARCHIVE)
    posts = parse_blog_index(archive)
    assert len(posts) == 3


def test_parse_blog_index_fields(tmp_path: Path):
    archive = tmp_path / "unchained-archive.md"
    archive.write_text(_SAMPLE_ARCHIVE)
    posts = parse_blog_index(archive)
    first = posts[0]
    assert first.title == "Zero CVEs in Production Java"
    assert first.url == "https://chainguard.dev/unchained/zero-cve-java"
    assert first.date == "March 15, 2024"
    assert "Chainguard" in first.full_content
    assert len(first.excerpt) <= 300


def test_parse_blog_index_no_date_post(tmp_path: Path):
    archive = tmp_path / "unchained-archive.md"
    archive.write_text(_SAMPLE_ARCHIVE)
    posts = parse_blog_index(archive)
    no_date = next(p for p in posts if p.title == "No-date post")
    assert no_date.date == ""


def test_parse_blog_index_missing_file(tmp_path: Path):
    posts = parse_blog_index(tmp_path / "nonexistent.md")
    assert posts == []


def test_parse_blog_index_excerpt_truncated(tmp_path: Path):
    long_content = "x" * 1000
    archive_text = f"""\
# Archive

---

## Long Post

*Source: https://chainguard.dev/unchained/long-post | June 1, 2024*

{long_content}

---
"""
    archive = tmp_path / "unchained-archive.md"
    archive.write_text(archive_text)
    posts = parse_blog_index(archive)
    assert len(posts) == 1
    assert len(posts[0].excerpt) == 300
    assert len(posts[0].full_content) > 300
