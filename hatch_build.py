"""Hatch build hook: compiles the Go scraper into a bundled binary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        bin_dir = root / "src" / "doc_suggester" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "scraper.exe" if sys.platform == "win32" else "scraper"
        output = bin_dir / binary_name

        print(f"[hatch-build] Compiling Go scraper → {output}")
        subprocess.run(
            ["go", "build", "-o", str(output), "."],
            cwd=root,
            check=True,
        )

        # Mark as an artifact so hatchling includes it even though it's gitignored
        build_data["artifacts"].append(f"src/doc_suggester/bin/{binary_name}")
