package config

import (
	"flag"
	"fmt"
	"os"
)

// Config holds all runtime configuration parsed from CLI flags.
type Config struct {
	OutputDir  string
	CacheDir   string
	Force      bool
	Only       string
	Lab        string
	Model      string
	YtDlpPath  string
	DecksDir   string
}

// Parse parses CLI flags and returns a Config. Exits on error.
func Parse() *Config {
	cfg := &Config{}

	flag.StringVar(&cfg.OutputDir, "output-dir", ".", "Output directory for generated files")
	flag.StringVar(&cfg.CacheDir, "cache-dir", "./cache", "Cache directory for transcripts, GitHub guides, and intermediate LLM output")
	flag.BoolVar(&cfg.Force, "force", false, "Ignore all caches; re-fetch and re-generate everything")
	flag.BoolVar(&cfg.Force, "fetch-all", false, "Alias for --force")
	flag.StringVar(&cfg.Only, "only", "", "Regenerate one output file only (e.g. labs-catalog.json)")
	flag.StringVar(&cfg.Lab, "lab", "", "Process only this lab ID (e.g. ll202509); implies --force for that lab")
	flag.StringVar(&cfg.Model, "model", "claude-sonnet-4-6", "Claude model to use for generation")
	flag.StringVar(&cfg.YtDlpPath, "ytdlp-path", "yt-dlp", "Path to yt-dlp binary")
	flag.StringVar(&cfg.DecksDir, "decks-dir", "../decks", "Directory containing PPTX slide decks")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "llgen — Chainguard Learning Labs generator\n\nUsage:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nEnvironment:\n  ANTHROPIC_API_KEY  Required for all generation steps\n")
	}

	flag.Parse()

	// --lab implies --force for that lab (handled in main by clearing that lab's intermediates)
	return cfg
}

// TranscriptDir returns the directory where VTT transcript files are cached.
// Supports two layouts:
//   - flat: files live directly in CacheDir (e.g. /tmp/ll-transcripts/*.en.vtt)
//   - nested: files live in CacheDir/transcripts/
func (c *Config) TranscriptDir() string {
	return c.CacheDir
}

// GitHubCacheDir returns the directory for cached GitHub guide markdown files.
func (c *Config) GitHubCacheDir() string {
	return c.CacheDir + "/github"
}

// CatalogCacheDir returns the per-lab catalog intermediate cache directory.
func (c *Config) CatalogCacheDir() string {
	return c.CacheDir + "/catalog"
}

// ImprovementsCacheDir returns the per-lab improvements intermediate cache directory.
func (c *Config) ImprovementsCacheDir() string {
	return c.CacheDir + "/improvements"
}

// PersonasCacheDir returns the per-lab personas intermediate cache directory.
func (c *Config) PersonasCacheDir() string {
	return c.CacheDir + "/personas"
}
