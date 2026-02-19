"""Async MCP client wrapping the Chainguard docs Docker MCP server."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_DOCKER_IMAGE = "ghcr.io/chainguard-dev/ai-docs:latest"


class DocsClient:
    """Async context manager that opens a single Docker MCP subprocess."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._cm: Any = None  # the stdio_client context manager
        self._session_cm: Any = None

    async def __aenter__(self) -> "DocsClient":
        server_params = StdioServerParameters(
            command="docker",
            args=["run", "--rm", "-i", _DOCKER_IMAGE, "serve-mcp"],
        )
        self._cm = stdio_client(server_params)
        read, write = await self._cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc_val, exc_tb)
        if self._cm is not None:
            await self._cm.__aexit__(exc_type, exc_val, exc_tb)

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

    async def search(self, query: str, max_results: int = 5) -> str:
        """Search docs (unreliable — prefer get_security_docs/get_tool_docs/get_image_docs)."""
        assert self._session is not None
        result = await self._session.call_tool(
            "search_docs",
            arguments={"query": query, "max_results": max_results},
        )
        return self._extract_text(result)

    async def get_image_docs(self, image_name: str) -> str:
        """Get documentation for a specific Chainguard image."""
        assert self._session is not None
        result = await self._session.call_tool(
            "get_image_docs",
            arguments={"image_name": image_name},
        )
        return self._extract_text(result)

    async def get_security_docs(self) -> str:
        """Get security-related documentation (CVEs, SBOMs, Cosign, etc.)."""
        assert self._session is not None
        result = await self._session.call_tool("get_security_docs", arguments={})
        return self._extract_text(result)

    async def get_tool_docs(self, tool_name: str) -> str:
        """Get documentation for a Chainguard tool (wolfi, apko, melange, chainctl)."""
        assert self._session is not None
        result = await self._session.call_tool(
            "get_tool_docs",
            arguments={"tool_name": tool_name},
        )
        return self._extract_text(result)

    async def list_images(self) -> str:
        """List all available Chainguard container images."""
        assert self._session is not None
        result = await self._session.call_tool("list_images", arguments={})
        return self._extract_text(result)
