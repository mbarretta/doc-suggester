"""Forge plugin wrapper for doc-suggester."""

from __future__ import annotations

import asyncio
from pathlib import Path

from forge_core.context import ExecutionContext
from forge_core.plugin import ResultStatus, ToolParam, ToolPlugin, ToolResult

from doc_suggester.suggester import suggest


class DocSuggesterPlugin:
    name = "doc-suggester"
    description = "Recommend relevant Chainguard blogs and docs for a prospect"
    version = "0.1.0"

    def get_params(self) -> list[ToolParam]:
        return [
            ToolParam(
                name="notes",
                description="SE notes or keywords about the prospect",
                required=True,
            ),
            ToolParam(
                name="refresh",
                description="Force blog archive refresh",
                type="bool",
                default=False,
            ),
            ToolParam(
                name="project_root",
                description="Path to the doc-suggester project root",
                default=".",
            ),
        ]

    def run(self, args: dict, ctx: ExecutionContext) -> ToolResult:
        ctx.progress(0.0, "Starting doc-suggester...")
        try:
            result = asyncio.run(
                suggest(
                    se_notes=args["notes"],
                    project_root=Path(args.get("project_root", ".")),
                    force_refresh=args.get("refresh", False),
                )
            )
            ctx.progress(1.0, "Done")
            return ToolResult(
                status=ResultStatus.SUCCESS,
                summary="Recommendations generated",
                data={"output": result},
            )
        except Exception as e:
            return ToolResult(status=ResultStatus.FAILURE, summary=f"Error: {e}")


def create_plugin() -> ToolPlugin:
    return DocSuggesterPlugin()
