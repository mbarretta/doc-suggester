"""Learning Labs management: freshness checks, llgen invocation, catalog parsing."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_LABS_STALE_DAYS = 30


@dataclass
class LabEntry:
    id: str
    title: str
    date: str           # "YYYY-MM"
    url: str            # lab_page_url if available, else recording_url
    recording_url: str
    technologies: list[str] = field(default_factory=list)
    chainguard_products: list[str] = field(default_factory=list)
    difficulty: str = ""
    intent_signals: list[str] = field(default_factory=list)
    summary: str = ""
    what_you_build: str = ""
    problems_addressed: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    related_labs: list[str] = field(default_factory=list)


def is_labs_stale(project_root: Path) -> bool:
    """Return True if labs-catalog.json is missing or older than _LABS_STALE_DAYS."""
    catalog = project_root / "output" / "labs-catalog.json"
    if not catalog.exists():
        return True
    mtime = datetime.fromtimestamp(catalog.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    return age.days > _LABS_STALE_DAYS


def _find_llgen() -> list[str]:
    """Return the command to invoke llgen.

    Prefers the binary bundled at install time. Falls back to `go run .`
    for development (uv run / editable install).
    """
    binary_name = "llgen.exe" if sys.platform == "win32" else "llgen"
    bundled = Path(__file__).parent / "bin" / binary_name
    if bundled.exists():
        bundled.chmod(0o755)
        return [str(bundled)]
    return ["go", "run", "."]


def refresh_labs(project_root: Path, force: bool = False) -> None:
    """Run llgen to refresh the labs catalog."""
    cmd = _find_llgen()
    args = [
        "--output-dir", str(project_root / "output"),
        "--cache-dir", str(project_root / "llgen-cache"),
        "--decks-dir", str(project_root / "decks"),
    ]
    if force:
        args.append("--force")
    # go run . requires cwd to be the Go source dir; the precompiled binary does not
    cwd = project_root / "llgen" if cmd == ["go", "run", "."] else project_root
    logger.debug("Running llgen: %s %s (cwd=%s)", cmd, args, cwd)
    sink = sys.stderr if logger.isEnabledFor(logging.DEBUG) else subprocess.DEVNULL
    try:
        subprocess.run(
            cmd + args,
            cwd=cwd,
            check=True,
            stdout=sink,
            stderr=sink,
        )
    except subprocess.CalledProcessError:
        logger.warning("llgen failed — using existing labs-catalog.json")


def load_labs(catalog_path: Path) -> list[LabEntry]:
    """Parse labs-catalog.json into a list of LabEntry objects."""
    if not catalog_path.exists():
        return []

    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    labs: list[LabEntry] = []
    for entry in data.get("labs", []):
        recording_url = entry.get("recording_url") or ""
        lab_page_url = entry.get("lab_page_url") or ""
        url = lab_page_url if lab_page_url else recording_url
        if not url:
            continue
        labs.append(LabEntry(
            id=entry.get("id", ""),
            title=entry.get("title", ""),
            date=entry.get("date", ""),
            url=url,
            recording_url=recording_url,
            technologies=entry.get("technologies", []),
            chainguard_products=entry.get("chainguard_products", []),
            difficulty=entry.get("difficulty", ""),
            intent_signals=entry.get("intent_signals", []),
            summary=entry.get("summary", ""),
            what_you_build=entry.get("what_you_build", ""),
            problems_addressed=entry.get("problems_addressed", []),
            prerequisites=entry.get("prerequisites", []),
            personas=entry.get("personas", []),
            related_labs=entry.get("related_labs", []),
        ))
    return labs


def build_labs_index_text(labs: list[LabEntry]) -> str:
    """Build a compact index string for the LLM prompt."""
    if not labs:
        return ""
    lines = ["## Learning Labs Index\n"]
    for lab in labs:
        tech_str = ", ".join(lab.technologies) if lab.technologies else ""
        signals_str = ", ".join(lab.intent_signals[:6]) if lab.intent_signals else ""
        lines.append(f"- **{lab.title}** ({lab.date}) [{lab.difficulty}]")
        lines.append(f"  ID: {lab.id} | URL: {lab.url}")
        if tech_str:
            lines.append(f"  Technologies: {tech_str}")
        if signals_str:
            lines.append(f"  Signals: {signals_str}")
        if lab.summary:
            lines.append(f"  Summary: {lab.summary[:200]}")
        lines.append("")
    return "\n".join(lines)


def format_lab_detail(lab: LabEntry) -> str:
    """Format a single lab's full details for tool result text."""
    lines = [f"# {lab.title}", f"**ID**: {lab.id}", f"**Date**: {lab.date}",
             f"**Difficulty**: {lab.difficulty}", f"**URL**: {lab.url}"]
    if lab.recording_url and lab.recording_url != lab.url:
        lines.append(f"**Recording**: {lab.recording_url}")
    if lab.technologies:
        lines.append(f"**Technologies**: {', '.join(lab.technologies)}")
    if lab.chainguard_products:
        lines.append(f"**Chainguard products**: {', '.join(lab.chainguard_products)}")
    if lab.personas:
        lines.append(f"**Personas**: {', '.join(lab.personas)}")
    if lab.summary:
        lines.append(f"\n**Summary**: {lab.summary}")
    if lab.what_you_build:
        lines.append(f"\n**What you build**: {lab.what_you_build}")
    if lab.problems_addressed:
        lines.append("\n**Problems addressed**:")
        for p in lab.problems_addressed:
            lines.append(f"- {p}")
    if lab.prerequisites:
        lines.append(f"\n**Prerequisites**: {', '.join(lab.prerequisites)}")
    if lab.intent_signals:
        lines.append(f"\n**Intent signals**: {', '.join(lab.intent_signals)}")
    if lab.related_labs:
        lines.append(f"\n**Related labs**: {', '.join(lab.related_labs)}")
    return "\n".join(lines)
