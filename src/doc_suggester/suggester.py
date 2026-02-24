"""Core LLM orchestration: generates content recommendations from SE notes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic

from doc_suggester.blog_manager import BlogPost, is_archive_stale, parse_blog_index, refresh_blogs
from doc_suggester.synopsis_generator import _url_to_slug, generate_synopses
from doc_suggester.docs_client import DocsClient
from doc_suggester.labs_manager import (
    LabEntry,
    build_labs_index_text,
    format_lab_detail,
    is_labs_stale,
    load_labs,
    refresh_labs,
)


_MODEL = "claude-sonnet-4-6"
_MAX_TURNS = 20

_SYSTEM_PROMPT_BASE = """\
You are a technical content advisor for Chainguard sales engineers. Given notes about a prospect, \
you identify the most relevant Chainguard blog posts and documentation pages.

You have access to:
1. A blog index below (title, URL, date, short excerpt) — use get_blog_post to read a full post
2. Tools to fetch Chainguard product documentation
3. A Learning Labs index (hands-on video sessions) — use get_lab to read full lab details

Workflow:
- Scan the blog index for relevant posts based on title and excerpt
- Fetch full content for the most promising posts using get_blog_post
- Fetch relevant documentation using get_security_docs, get_tool_docs, or get_image_docs
- Use search_docs only as a fallback when other tools don't surface what you need
- Fetch full lab details using get_lab before recommending a lab
- Select the 5–10 most relevant resources before writing your final output

"""

_OUTPUT_FORMAT_MD = """\
Output format for each recommendation:
### N. [Type] Title
**URL**: <url>
**Date**: <date> (for blog posts)
**Lab page**: <url> (for Learning Labs)
**Recording**: <url> (for Learning Labs)
**Difficulty**: <level> (for Learning Labs)
**Why relevant**: 1–2 sentence explanation tied to the prospect's specific concerns

When a blog post and a documentation page conflict, prefer the more recently dated source. \
If conflicts exist, add a "## Content Conflicts" section at the end noting them.

If no conflicts: end with `*No content conflicts detected.*`
"""

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _build_system_prompt(output_format: str) -> str:
    if output_format == "email":
        fmt = (_PROMPTS_DIR / "email_format.txt").read_text(encoding="utf-8")
    else:
        fmt = _OUTPUT_FORMAT_MD
    return _SYSTEM_PROMPT_BASE + fmt


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
    {
        "name": "get_lab",
        "description": "Get full details for a Chainguard Learning Lab by ID (e.g. 'll202509'). Use when the index shows a lab may be relevant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lab_id": {"type": "string"},
            },
            "required": ["lab_id"],
        },
    },
]


def _build_blog_index_text(posts: list[BlogPost], synopses: dict[str, str] = {}) -> str:
    lines = ["## Blog Index\n"]
    for post in posts:
        date_part = f" | {post.date}" if post.date else ""
        lines.append(f"- **{post.title}**{date_part}")
        lines.append(f"  URL: {post.url}")
        slug = _url_to_slug(post.url)
        blurb = synopses.get(slug) or post.excerpt[:200]
        lines.append(f"  Synopsis: {blurb}")
        lines.append("")
    return "\n".join(lines)


async def _dispatch_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    post_by_url: dict[str, BlogPost],
    docs: DocsClient,
    lab_by_id: dict[str, LabEntry],
) -> str:
    if tool_name == "get_blog_post":
        url = tool_input.get("url", "")
        post = post_by_url.get(url)
        return post.full_content if post else f"Blog post not found in archive: {url}"
    if tool_name == "search_docs":
        return await docs.search(
            query=tool_input["query"],
            max_results=tool_input.get("max_results", 5),
        )
    if tool_name == "get_security_docs":
        return await docs.get_security_docs()
    if tool_name == "get_tool_docs":
        return await docs.get_tool_docs(tool_input["tool_name"])
    if tool_name == "get_image_docs":
        return await docs.get_image_docs(tool_input["image_name"])
    if tool_name == "get_lab":
        lab_id = tool_input.get("lab_id", "")
        lab = lab_by_id.get(lab_id)
        return format_lab_detail(lab) if lab else f"Lab not found: {lab_id}"
    return f"Unknown tool: {tool_name}"


async def suggest(
    se_notes: str,
    project_root: Path,
    force_refresh: bool = False,
    output_format: str = "md",
) -> str:
    """Generate content recommendations for SE notes.

    Args:
        se_notes: Free-form text describing the prospect's interests/concerns.
        project_root: Path to the doc-suggester repo root (contains main.go).
        force_refresh: If True, run the Go scraper regardless of archive age.
        output_format: "md" for ranked markdown (default), "email" for a follow-up email draft.

    Returns:
        Formatted recommendations in the requested format.
    """
    # 1. Refresh blogs if needed
    if force_refresh or is_archive_stale(project_root):
        refresh_blogs(project_root, force=force_refresh)

    # 2. Refresh labs if needed
    if force_refresh or is_labs_stale(project_root):
        refresh_labs(project_root, force=force_refresh)

    # 3. Parse blog index
    archive_path = project_root / "output" / "unchained-archive.md"
    posts = parse_blog_index(archive_path)
    synopses = await generate_synopses(project_root, posts)
    blog_index_text = _build_blog_index_text(posts, synopses)
    post_by_url = {p.url: p for p in posts}

    # 4. Parse labs catalog
    labs = load_labs(project_root / "output" / "labs-catalog.json")
    lab_by_id = {lab.id: lab for lab in labs}
    labs_index_text = build_labs_index_text(labs)

    # 5. Run multi-turn tool use with a single DocsClient session
    client = anthropic.AsyncAnthropic()
    system_prompt = _build_system_prompt(output_format)
    user_content = f"SE notes about prospect:\n\n{se_notes}\n\n{blog_index_text}"
    if labs_index_text:
        user_content += f"\n\n{labs_index_text}"
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": user_content,
        }
    ]

    async with DocsClient() as docs:
        for _ in range(_MAX_TURNS):
            response = await client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=_TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result_text = await _dispatch_tool(block.name, block.input, post_by_url, docs, lab_by_id)
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
