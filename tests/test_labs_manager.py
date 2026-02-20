"""Tests for labs_manager module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from doc_suggester.labs_manager import (
    LabEntry,
    build_labs_index_text,
    is_labs_stale,
    load_labs,
)

# ─── helpers ─────────────────────────────────────────────────────────────────

_SAMPLE_ENTRY = {
    "id": "ll202509",
    "title": "Java Zero-CVE Lab",
    "date": "2025-09",
    "era": "new-format",
    "status": "published",
    "recording_url": "https://www.youtube.com/watch?v=abc123",
    "lab_page_url": "https://edu.chainguard.dev/software-security/learning-labs/ll202509/",
    "technologies": ["Java", "Docker", "grype"],
    "chainguard_products": ["Chainguard Containers (Java)"],
    "difficulty": "beginner",
    "intent_signals": ["Java CVEs", "container security", "Java security", "zero CVE", "CVE reduction", "Java images", "extra signal"],
    "summary": "Reduce CVEs in Java container images using Chainguard.",
    "what_you_build": "A Java app with zero CVEs.",
    "problems_addressed": ["High CVE count in Java images"],
    "prerequisites": ["Docker"],
    "personas": ["Java developer", "DevSecOps"],
    "related_labs": ["ll202508"],
}


def _make_catalog(tmp_path: Path, entries: list[dict]) -> Path:
    catalog = tmp_path / "output" / "labs-catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps({"labs": entries}))
    return catalog


# ─── is_labs_stale ────────────────────────────────────────────────────────────


def test_is_labs_stale_no_file(tmp_path: Path):
    (tmp_path / "output").mkdir()
    assert is_labs_stale(tmp_path) is True


def test_is_labs_stale_fresh(tmp_path: Path):
    catalog = _make_catalog(tmp_path, [])
    # mtime is effectively now — well within 30 days
    assert is_labs_stale(tmp_path) is False


def test_is_labs_stale_old(tmp_path: Path):
    catalog = _make_catalog(tmp_path, [])
    # Set mtime to 31 days ago
    old_mtime = time.time() - (31 * 24 * 3600)
    import os
    os.utime(catalog, (old_mtime, old_mtime))
    assert is_labs_stale(tmp_path) is True


# ─── load_labs ────────────────────────────────────────────────────────────────


def test_load_labs_missing_file(tmp_path: Path):
    result = load_labs(tmp_path / "output" / "labs-catalog.json")
    assert result == []


def test_load_labs_parses_entry(tmp_path: Path):
    catalog = _make_catalog(tmp_path, [_SAMPLE_ENTRY])
    labs = load_labs(catalog)
    assert len(labs) == 1
    lab = labs[0]
    assert lab.id == "ll202509"
    assert lab.title == "Java Zero-CVE Lab"
    assert lab.date == "2025-09"
    assert lab.difficulty == "beginner"
    assert "Java" in lab.technologies
    assert "Java CVEs" in lab.intent_signals
    assert lab.summary == "Reduce CVEs in Java container images using Chainguard."
    assert lab.personas == ["Java developer", "DevSecOps"]
    assert lab.related_labs == ["ll202508"]


def test_load_labs_prefers_lab_page_url(tmp_path: Path):
    catalog = _make_catalog(tmp_path, [_SAMPLE_ENTRY])
    labs = load_labs(catalog)
    assert labs[0].url == "https://edu.chainguard.dev/software-security/learning-labs/ll202509/"


def test_load_labs_falls_back_to_recording_url(tmp_path: Path):
    entry = dict(_SAMPLE_ENTRY, lab_page_url=None)
    catalog = _make_catalog(tmp_path, [entry])
    labs = load_labs(catalog)
    assert labs[0].url == "https://www.youtube.com/watch?v=abc123"


def test_load_labs_skips_entry_without_url(tmp_path: Path):
    entry = dict(_SAMPLE_ENTRY, recording_url="", lab_page_url=None)
    catalog = _make_catalog(tmp_path, [entry])
    labs = load_labs(catalog)
    assert labs == []


# ─── build_labs_index_text ───────────────────────────────────────────────────


def test_build_labs_index_text_empty():
    result = build_labs_index_text([])
    assert result == ""


def test_build_labs_index_text_includes_fields():
    lab = LabEntry(
        id="ll202509",
        title="Java Zero-CVE Lab",
        date="2025-09",
        url="https://edu.chainguard.dev/software-security/learning-labs/ll202509/",
        recording_url="https://www.youtube.com/watch?v=abc123",
        technologies=["Java", "Docker"],
        difficulty="beginner",
        intent_signals=["Java CVEs", "container security", "Java security", "zero CVE", "CVE reduction", "Java images"],
        summary="Reduce CVEs in Java container images.",
    )
    text = build_labs_index_text([lab])
    assert "Java Zero-CVE Lab" in text
    assert "ll202509" in text
    assert "https://edu.chainguard.dev/software-security/learning-labs/ll202509/" in text
    assert "Java CVEs" in text
    assert "Reduce CVEs" in text
