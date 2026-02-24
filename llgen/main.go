package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"llgen/data"
	"llgen/internal/claude"
	"llgen/internal/collect"
	"llgen/internal/config"
	"llgen/internal/generate"
	"llgen/internal/transform"
)

func main() {
	cfg := config.Parse()

	apiKey := os.Getenv("ANTHROPIC_API_KEY")
	if apiKey == "" {
		log.Fatal("ANTHROPIC_API_KEY environment variable is required")
	}

	ctx := context.Background()

	// Determine which labs to process.
	// --lab implies --force for the cache dirs of that lab.
	labs := data.Labs
	if cfg.Lab != "" {
		found := false
		for _, l := range data.Labs {
			if l.ID == cfg.Lab {
				labs = []data.LabMeta{l}
				found = true
				break
			}
		}
		if !found {
			log.Fatalf("lab %q not found in lab map", cfg.Lab)
		}
		// --lab implies force for that single lab's intermediates
		cfg.Force = true
	}

	// Ensure required directories exist.
	cacheDirs := []string{
		cfg.CacheDir,
		cfg.GitHubCacheDir(),
		cfg.CatalogCacheDir(),
		cfg.OutputDir,
	}
	for _, dir := range cacheDirs {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			log.Fatalf("mkdir %s: %v", dir, err)
		}
	}

	// Phase 1: Collect playlist metadata (best-effort; used for titles/dates).
	fmt.Println("==> Fetching playlist metadata...")
	playlistInfo, err := collect.FetchPlaylistInfo(cfg)
	if err != nil {
		log.Printf("Warning: could not fetch playlist info: %v", err)
		playlistInfo = map[string]collect.VideoInfo{}
	}

	// Phase 1: Download transcripts.
	fmt.Println("==> Downloading transcripts...")
	for _, lab := range labs {
		if err := collect.DownloadTranscript(cfg, lab); err != nil {
			log.Printf("Warning: transcript %s (%s): %v", lab.ID, lab.VideoID, err)
		}
	}

	// Phase 1: Fetch GitHub guides.
	fmt.Println("==> Fetching GitHub guides...")
	for _, lab := range labs {
		if lab.GitHubID == "" {
			continue
		}
		if _, err := collect.FetchGitHubGuide(cfg, lab.GitHubID); err != nil {
			log.Printf("Warning: GitHub guide %s: %v", lab.GitHubID, err)
		}
	}

	// Phase 2: Build corpora (transcript + guide + deck per lab).
	fmt.Println("==> Building lab corpora...")
	corpora := make(map[string]*transform.LabCorpus)
	for _, lab := range labs {
		corpus, err := transform.BuildCorpus(cfg, lab)
		if err != nil {
			log.Printf("Warning: corpus build %s: %v", lab.ID, err)
			corpus = &transform.LabCorpus{Lab: lab}
		}
		// Populate title/date from playlist metadata
		if info, ok := playlistInfo[lab.VideoID]; ok {
			corpus.Title = info.Title
			corpus.UploadDate = info.UploadDate
		}
		corpora[lab.ID] = corpus
	}

	// Phase 3: Generate output files in dependency order.
	claudeClient := claude.NewClient(apiKey, cfg.Model)

	only := cfg.Only
	runAll := only == ""

	if runAll || only == "learning-labs-index.md" {
		fmt.Println("==> Generating learning-labs-index.md...")
		if err := generate.Index(ctx, claudeClient, cfg, data.Labs, playlistInfo); err != nil {
			log.Fatalf("generate index: %v", err)
		}
	}

	if runAll || only == "labs-catalog.json" {
		fmt.Println("==> Generating labs-catalog.json...")
		if err := generate.Catalog(ctx, claudeClient, cfg, labs, corpora); err != nil {
			log.Fatalf("generate catalog: %v", err)
		}
	}

	if runAll || only == "recommender-system-prompt.md" {
		// Requires labs-catalog.json to exist
		catalogPath := filepath.Join(cfg.OutputDir, "labs-catalog.json")
		if _, err := os.Stat(catalogPath); os.IsNotExist(err) {
			log.Fatalf("recommender requires labs-catalog.json; run catalog generation first or use --only labs-catalog.json")
		}
		fmt.Println("==> Generating recommender-system-prompt.md...")
		if err := generate.Recommender(ctx, claudeClient, cfg); err != nil {
			log.Fatalf("generate recommender: %v", err)
		}
	}

	fmt.Println("==> Done.")
}
