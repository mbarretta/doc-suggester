"""CLI entry point for doc-suggester-cgr."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def _status(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        metavar="DIR",
        default=None,
        help="Path to the doc-suggester-cgr data directory (default: ~/.local/share/doc-suggester-cgr).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="doc-suggester-cgr",
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
    _add_common_args(parser)
    return parser.parse_args(argv)


async def _run_init(project_root: Path) -> None:
    """Pre-fetch and process all data sources for first-run readiness."""
    from doc_suggester_cgr.blog_manager import parse_blog_index, refresh_blogs
    from doc_suggester_cgr.labs_manager import refresh_labs
    from doc_suggester_cgr.synopsis_generator import generate_synopses

    _status("Refreshing blog archive and Learning Labs catalog...")
    await asyncio.gather(
        asyncio.to_thread(refresh_blogs, project_root, force=True),
        asyncio.to_thread(refresh_labs, project_root, force=True),
    )

    archive_path = project_root / "output" / "unchained-archive.md"
    posts = parse_blog_index(archive_path)
    if posts:
        _status("Generating blog synopses (this may take a minute on first run)...")
        await generate_synopses(project_root, posts)
    else:
        _status("Warning: no blog posts found after refresh — skipping synopsis generation.")

    _status("Init complete. Run 'doc-suggester-cgr' normally to get recommendations.")


def _resolve_project_root(explicit: str | None) -> Path:
    # 1. Explicit --project-root flag
    if explicit:
        return Path(explicit).resolve()
    # 2. Walk up from this file — works for `uv run` and development installs
    candidate = Path(__file__).resolve().parent
    while candidate != candidate.parent:  # stop at filesystem root
        if (candidate / "main.go").exists():
            return candidate
        candidate = candidate.parent
    # 3. Standalone (uv tool install): use a per-user data directory
    data_dir = Path.home() / ".local" / "share" / "doc-suggester-cgr"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main(argv: list[str] | None = None) -> None:
    # Handle 'init' subcommand before full argparse so it doesn't conflict with
    # positional notes arguments.
    raw = argv if argv is not None else sys.argv[1:]
    if raw and raw[0] == "init":
        init_parser = argparse.ArgumentParser(prog="doc-suggester-cgr init", add_help=True)
        _add_common_args(init_parser)
        init_args = init_parser.parse_args(raw[1:])
        _setup_logging(init_args.verbose)
        project_root = _resolve_project_root(init_args.project_root)
        asyncio.run(_run_init(project_root))
        return

    args = _parse_args(argv)
    _setup_logging(args.verbose)

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

    from doc_suggester_cgr.suggester import suggest

    result = asyncio.run(suggest(
        se_notes=notes,
        project_root=project_root,
        force_refresh=args.refresh,
        output_format=args.format,
    ))
    print(result)


if __name__ == "__main__":
    main()
