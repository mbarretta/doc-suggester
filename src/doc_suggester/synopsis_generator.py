"""LLM-based synopsis generation for blog posts, cached in output/blog-synopses.json."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import anthropic

from doc_suggester.blog_manager import BlogPost

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_CONCURRENCY = 10

_SYNOPSES_PATH = Path("output") / "blog-synopses.json"


def _url_to_slug(url: str) -> str:
    """Extract slug from URL — matches checkpoint.json key format."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def load_synopses(project_root: Path) -> dict[str, str]:
    """Read output/blog-synopses.json; returns {} if missing or corrupt."""
    path = project_root / _SYNOPSES_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def generate_synopses(project_root: Path, posts: list[BlogPost]) -> dict[str, str]:
    """Generate and cache synopses for posts that don't have one yet.

    Returns the full synopses dict (existing + newly generated).
    """
    synopses = load_synopses(project_root)
    missing = [p for p in posts if _url_to_slug(p.url) not in synopses]

    if not missing:
        return synopses

    logger.info("Generating synopses for %d posts...", len(missing))
    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _generate_one(post: BlogPost) -> tuple[str, str | None]:
        slug = _url_to_slug(post.url)
        prompt = (
            "Generate an information-retrieval synopsis for this Chainguard blog post.\n"
            "Output ONLY the synopsis — no preamble or explanation.\n"
            "Format: semicolon-separated key topics, technologies, problems addressed, and use cases.\n"
            "Target: 100–150 characters.\n\n"
            f"Title: {post.title}\n\n"
            f"Content:\n{post.full_content[:3000]}"
        )
        async with semaphore:
            try:
                response = await client.messages.create(
                    model=_MODEL,
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = next(
                    (b.text for b in response.content if hasattr(b, "text")), None
                )
                return slug, text
            except Exception as exc:
                logger.warning("Failed to generate synopsis for %s: %s", slug, exc)
                return slug, None

    results = await asyncio.gather(*(_generate_one(p) for p in missing))

    for slug, synopsis in results:
        if synopsis:
            synopses[slug] = synopsis

    path = project_root / _SYNOPSES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(sorted(synopses.items())), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return synopses
