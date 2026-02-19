"""CLI entry point for doc-suggester."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="doc-suggester",
        description="Recommend relevant Chainguard blogs and docs given SE notes about a prospect.",
    )
    parser.add_argument(
        "notes",
        nargs="*",
        metavar="NOTES",
        help="SE notes text (reads from stdin if omitted and --notes-file not given).",
    )
    parser.add_argument(
        "--format",
        choices=["md", "email"],
        default="md",
        help="Output format: 'md' for ranked markdown (default), 'email' for a follow-up email draft.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force blog archive refresh regardless of staleness.",
    )
    parser.add_argument(
        "--notes-file",
        metavar="FILE",
        help="Read SE notes from a file instead of positional args or stdin.",
    )
    parser.add_argument(
        "--project-root",
        metavar="DIR",
        default=None,
        help="Path to the doc-suggester data directory (default: ~/.local/share/doc-suggester).",
    )
    return parser.parse_args(argv)


def _resolve_project_root(explicit: str | None) -> Path:
    # 1. Explicit --project-root flag
    if explicit:
        return Path(explicit).resolve()
    # 2. Walk up from this file — works for `uv run` and development installs
    here = Path(__file__).resolve().parent
    for candidate in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        if (candidate / "main.go").exists():
            return candidate
    # 3. Standalone (uv tool install): use a per-user data directory
    data_dir = Path.home() / ".local" / "share" / "doc-suggester"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # Resolve SE notes text
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8").strip()
    elif args.notes:
        notes = " ".join(args.notes)
    elif not sys.stdin.isatty():
        notes = sys.stdin.read().strip()
    else:
        print("Error: provide SE notes as arguments, via --notes-file, or via stdin.", file=sys.stderr)
        sys.exit(1)

    if not notes:
        print("Error: SE notes are empty.", file=sys.stderr)
        sys.exit(1)

    project_root = _resolve_project_root(args.project_root)

    from doc_suggester.suggester import suggest

    result = asyncio.run(suggest(
        se_notes=notes,
        project_root=project_root,
        force_refresh=args.refresh,
        output_format=args.format,
    ))
    print(result)


if __name__ == "__main__":
    main()
