"""Forge plugin wrapper for doc-suggester."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from forge_core.context import ExecutionContext
from forge_core.plugin import ResultStatus, ToolParam, ToolPlugin, ToolResult

from doc_suggester.suggester import suggest

_DEFAULT_DATA_DIR = str(Path.home() / ".local" / "share" / "doc-suggester")


class DocSuggesterPlugin:
    name = "doc-suggester"
    description = "Recommend relevant Chainguard blogs and docs for a prospect"
    version = "0.1.0"
    requires_auth = False  # uses ANTHROPIC_API_KEY, not chainctl

    def get_params(self) -> list[ToolParam]:
        return [
            ToolParam(
                name="notes",
                description="SE notes or keywords about the prospect",
                required=True,
            ),
            ToolParam(
                name="format",
                description="Output format",
                choices=["md", "email"],
                default="md",
            ),
            ToolParam(
                name="refresh",
                description="Force blog archive refresh",
                type="bool",
                default=False,
            ),
            ToolParam(
                name="project_root",
                description=f"Path to the doc-suggester data directory (default: {_DEFAULT_DATA_DIR})",
                type="path",
            ),
        ]

    def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        ctx.progress(0.0, "Starting doc-suggester...")

        if ctx.is_cancelled:
            return ToolResult(status=ResultStatus.CANCELLED, summary="Cancelled by user")

        raw_root = args.get("project_root")
        project_root = Path(raw_root) if raw_root else Path(_DEFAULT_DATA_DIR)
        project_root.mkdir(parents=True, exist_ok=True)

        ctx.progress(0.1, "Running analysis...")
        try:
            result = asyncio.run(
                suggest(
                    se_notes=args["notes"],
                    project_root=project_root,
                    force_refresh=args.get("refresh", False),
                    output_format=args.get("format", "md"),
                )
            )
        except Exception as e:
            logging.exception("doc-suggester failed")
            return ToolResult(status=ResultStatus.FAILURE, summary=f"Error: {e}")

        ctx.progress(1.0, "Done")
        return ToolResult(
            status=ResultStatus.SUCCESS,
            summary="Recommendations generated",
            data={"output": result},
        )


def create_plugin() -> ToolPlugin:
    return DocSuggesterPlugin()
