"""Core LLM orchestration: generates content recommendations from SE notes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic

from doc_suggester.blog_manager import BlogPost, is_archive_stale, parse_blog_index, refresh_blogs
from doc_suggester.docs_client import DocsClient


_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
You are a technical content advisor for Chainguard sales engineers. Given notes about a prospect, \
you recommend the most relevant Chainguard blog posts and documentation pages.

You have access to:
1. A blog index below (title, URL, date, short excerpt) — use get_blog_post to read a full post
2. Tools to fetch Chainguard product documentation

Workflow:
- Scan the blog index for relevant posts based on title and excerpt
- Fetch full content for the most promising posts using get_blog_post
- Fetch relevant documentation using get_security_docs, get_tool_docs, or get_image_docs
- Use search_docs only as a fallback when other tools don't surface what you need
- Produce a ranked markdown list of 5–10 recommendations

Output format for each recommendation:
### N. [Type] Title
**URL**: <url>
**Date**: <date> (for blog posts)
**Why relevant**: 1–2 sentence explanation tied to the prospect's specific concerns

When a blog post and a documentation page conflict, prefer the more recently dated source. \
If conflicts exist, add a "## Content Conflicts" section at the end noting them.

If no conflicts: end with `*No content conflicts detected.*`
"""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_blog_post",
        "description": "Fetch the full content of a blog post by its URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL of the blog post to fetch."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "search_docs",
        "description": "Search Chainguard documentation. Unreliable — use get_security_docs, get_tool_docs, or get_image_docs first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_security_docs",
        "description": "Fetch Chainguard security documentation (CVEs, SBOMs, Cosign, signing, etc.).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_tool_docs",
        "description": "Fetch docs for a Chainguard tool. tool_name must be one of: wolfi, apko, melange, chainctl.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "enum": ["wolfi", "apko", "melange", "chainctl"],
                }
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "get_image_docs",
        "description": "Fetch documentation for a specific Chainguard container image (e.g. 'java', 'python', 'nginx').",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_name": {"type": "string", "description": "Image name, e.g. 'java', 'python'."}
            },
            "required": ["image_name"],
        },
    },
]


def _build_blog_index_text(posts: list[BlogPost]) -> str:
    lines = ["## Blog Index\n"]
    for post in posts:
        date_part = f" | {post.date}" if post.date else ""
        lines.append(f"- **{post.title}**{date_part}")
        lines.append(f"  URL: {post.url}")
        lines.append(f"  Excerpt: {post.excerpt[:200]}")
        lines.append("")
    return "\n".join(lines)


async def suggest(
    se_notes: str,
    project_root: Path,
    force_refresh: bool = False,
) -> str:
    """Generate content recommendations for SE notes.

    Args:
        se_notes: Free-form text describing the prospect's interests/concerns.
        project_root: Path to the doc-suggester repo root (contains main.go).
        force_refresh: If True, run the Go scraper regardless of archive age.

    Returns:
        Formatted markdown recommendations.
    """
    # 1. Refresh blogs if needed
    if force_refresh or is_archive_stale(project_root):
        refresh_blogs(project_root, force=force_refresh)

    # 2. Parse blog index
    archive_path = project_root / "output" / "unchained-archive.md"
    posts = parse_blog_index(archive_path)
    blog_index_text = _build_blog_index_text(posts)
    post_by_url = {p.url: p for p in posts}

    # 3. Run multi-turn tool use with a single DocsClient session
    client = anthropic.AsyncAnthropic()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": f"SE notes about prospect:\n\n{se_notes}\n\n{blog_index_text}",
        }
    ]

    async with DocsClient() as docs:
        while True:
            response = await client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            # Collect assistant message
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                result_text: str

                if tool_name == "get_blog_post":
                    url = tool_input.get("url", "")
                    post = post_by_url.get(url)
                    if post:
                        result_text = post.full_content
                    else:
                        result_text = f"Blog post not found in archive: {url}"

                elif tool_name == "search_docs":
                    result_text = await docs.search(
                        query=tool_input["query"],
                        max_results=tool_input.get("max_results", 5),
                    )

                elif tool_name == "get_security_docs":
                    result_text = await docs.get_security_docs()

                elif tool_name == "get_tool_docs":
                    result_text = await docs.get_tool_docs(tool_input["tool_name"])

                elif tool_name == "get_image_docs":
                    result_text = await docs.get_image_docs(tool_input["image_name"])

                else:
                    result_text = f"Unknown tool: {tool_name}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

    # Extract final text response
    for block in response.content:
        if hasattr(block, "text"):
            return block.text

    return "No recommendations generated."
