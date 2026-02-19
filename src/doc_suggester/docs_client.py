"""Async MCP client wrapping the Chainguard docs Docker MCP server."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

_DOCKER_IMAGE = "ghcr.io/chainguard-dev/ai-docs:latest"


class DocsClient:
    """Async context manager that opens a single Docker MCP subprocess."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "DocsClient":
        server_params = StdioServerParameters(
            command="docker",
            args=["run", "--rm", "-i", _DOCKER_IMAGE, "serve-mcp"],
        )
        # Route subprocess stderr to /dev/null unless DEBUG logging is active.
        # (anyio requires a real file descriptor, so a Python-level wrapper won't work.)
        if logger.isEnabledFor(logging.DEBUG):
            errlog = sys.stderr
        else:
            errlog = open(os.devnull, "w")

        async with AsyncExitStack() as stack:
            if errlog is not sys.stderr:
                stack.callback(errlog.close)
            logger.debug("Starting MCP docs server via Docker")
            read, write = await stack.enter_async_context(stdio_client(server_params, errlog=errlog))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session = session
            self._stack = stack.pop_all()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._stack is not None:
            await self._stack.aclose()

    def _extract_text(self, result: Any) -> str:
        """Extract text content from an MCP tool result."""
        if hasattr(result, "content"):
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            return "\n".join(parts)
        return str(result)

    async def _call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        if self._session is None:
            raise RuntimeError("DocsClient must be used as an async context manager")
        result = await self._session.call_tool(name, arguments=arguments or {})
        return self._extract_text(result)

    async def search(self, query: str, max_results: int = 5) -> str:
        """Search docs (unreliable — prefer get_security_docs/get_tool_docs/get_image_docs)."""
        return await self._call_tool("search_docs", {"query": query, "max_results": max_results})

    async def get_image_docs(self, image_name: str) -> str:
        """Get documentation for a specific Chainguard image."""
        return await self._call_tool("get_image_docs", {"image_name": image_name})

    async def get_security_docs(self) -> str:
        """Get security-related documentation (CVEs, SBOMs, Cosign, etc.)."""
        return await self._call_tool("get_security_docs")

    async def get_tool_docs(self, tool_name: str) -> str:
        """Get documentation for a Chainguard tool (wolfi, apko, melange, chainctl)."""
        return await self._call_tool("get_tool_docs", {"tool_name": tool_name})
