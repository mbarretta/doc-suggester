# doc-suggester

Given SE notes about a prospect, recommends relevant Chainguard blog posts and documentation pages using Claude.

## How it works

1. Checks if the blog archive is fresh (< 7 days old); runs the Go scraper if not
2. Parses the archive into a lightweight index of ~500 posts
3. Starts the Chainguard docs MCP server via Docker
4. Calls Claude (`claude-sonnet-4-6`) with the blog index and doc tools — Claude fetches full content on demand and returns a ranked markdown list

## Prerequisites

- [Go](https://go.dev/dl/) — for the blog scraper
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- [Docker](https://docs.docker.com/get-docker/) — for the docs MCP server
- `ANTHROPIC_API_KEY` set in your environment

## Install

### Standalone (recommended)

Compiles the Go scraper and installs `doc-suggester` as a global command — no virtualenv activation or `uv run` prefix needed.

```bash
git clone https://github.com/mbarretta/doc-suggester
uv tool install ./doc-suggester
```

The blog archive is stored in `~/.local/share/doc-suggester/` and refreshed automatically when it's more than 7 days old.

### Development

```bash
git clone https://github.com/mbarretta/doc-suggester
cd doc-suggester
uv sync
```

## Usage

### Basic

```bash
# Standalone
doc-suggester "prospect worried about Java CVEs in production"

# Development (from repo root)
uv run doc-suggester "prospect worried about Java CVEs in production"
```

### Read notes from a file

```bash
doc-suggester --notes-file notes.txt
```

### Pipe from stdin

```bash
echo "fintech company, needs FIPS compliance, currently on Ubuntu base images" | doc-suggester
```

### Output as a follow-up email

```bash
doc-suggester --format email "prospect worried about Java CVEs"
```

Produces a ready-to-send follow-up email — warm opener, resources woven into prose paragraphs with inline URLs, and a closing offer to follow up. The default (`--format md`) returns a ranked markdown list with titles, URLs, dates, and relevance explanations.

### Force a blog archive refresh

```bash
doc-suggester --refresh "prospect interested in SLSA compliance"
```

The `--refresh` flag re-runs the Go scraper regardless of archive age. Without it, the archive is refreshed automatically when it's more than 7 days old.

## Forge plugin

The `forge-plugin/` directory contains a thin wrapper that registers `doc-suggester` as an external Forge plugin. To install it for development:

```bash
uv pip install -e ./forge-plugin
```

Then invoke it via Forge:

```bash
forge doc-suggester --notes "prospect worried about Java CVEs"
forge doc-suggester --notes "prospect worried about Java CVEs" --output-format email
```

See `forge-plugin/pyproject.toml` for the `plugins-registry.yaml` entry.

## Development

```bash
# Run tests
uv run pytest tests/

# Run without installing
uv run python -m doc_suggester "some SE notes"
```
