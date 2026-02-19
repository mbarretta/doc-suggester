"""Blog archive management: freshness checks, parsing, and Go scraper invocation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class BlogPost:
    title: str
    url: str
    date: str
    excerpt: str
    full_content: str


_STALE_DAYS = 7

# Matches archive entries: ## Title\n\n*Source: URL | Date*\n\nContent\n\n---
_ENTRY_RE = re.compile(
    r"^## (.+?)\n\n\*Source: (https?://[^\s|]+?)(?:\s*\|\s*([^\*]+))?\*\n\n([\s\S]*?)(?=\n\n---)",
    re.MULTILINE,
)

_DATE_FORMATS = [
    "%B %d, %Y",   # January 05, 2024
    "%B %-d, %Y",  # January 5, 2024 (Linux strptime)
    "%B %d %Y",    # January 05 2024
]


def _parse_date(date_str: str) -> datetime | None:
    """Parse a date string like 'January 5, 2024' into a datetime."""
    date_str = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Also try ISO format (Go scraper may emit YYYY-MM-DD)
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def get_most_recent_blog_date(project_root: Path) -> datetime | None:
    """Return the most recent blog post date from checkpoint.json, or None."""
    checkpoint_path = project_root / "output" / "checkpoint.json"
    if not checkpoint_path.exists():
        return None
    try:
        data: dict = json.loads(checkpoint_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    most_recent: datetime | None = None
    for entry in data.values():
        raw_date = entry.get("date", "")
        if not raw_date:
            continue
        parsed = _parse_date(raw_date)
        if parsed and (most_recent is None or parsed > most_recent):
            most_recent = parsed
    return most_recent


def is_archive_stale(project_root: Path) -> bool:
    """Return True if the archive is missing or the newest post is older than STALE_DAYS."""
    archive = project_root / "output" / "unchained-archive.md"
    if not archive.exists():
        return True
    most_recent = get_most_recent_blog_date(project_root)
    if most_recent is None:
        return True
    age = datetime.now(timezone.utc) - most_recent
    return age.days > _STALE_DAYS


def _find_scraper() -> list[str]:
    """Return the command to invoke the Go scraper.

    Prefers the binary bundled at install time. Falls back to `go run main.go`
    for development (uv run / editable install).
    """
    binary_name = "scraper.exe" if sys.platform == "win32" else "scraper"
    bundled = Path(__file__).parent / "bin" / binary_name
    if bundled.exists():
        bundled.chmod(0o755)
        return [str(bundled)]
    return ["go", "run", "main.go"]


def refresh_blogs(project_root: Path, force: bool = False) -> None:
    """Run the Go scraper to refresh the blog archive."""
    cmd = _find_scraper()
    if force:
        cmd.append("-force")
    print(f"[doc-suggester] Running scraper in {project_root}", file=sys.stderr)
    subprocess.run(cmd, cwd=project_root, check=True, stderr=sys.stderr)


def parse_blog_index(archive_path: Path) -> list[BlogPost]:
    """Parse unchained-archive.md into a list of BlogPost objects."""
    if not archive_path.exists():
        return []

    text = archive_path.read_text(encoding="utf-8")
    posts: list[BlogPost] = []

    for match in _ENTRY_RE.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).strip()
        date = (match.group(3) or "").strip()
        full_content = match.group(4).strip()
        excerpt = full_content[:300]
        posts.append(BlogPost(title=title, url=url, date=date, excerpt=excerpt, full_content=full_content))

    return posts
