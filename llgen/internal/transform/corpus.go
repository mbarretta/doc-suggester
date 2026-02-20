package transform

import (
	"os"
	"path/filepath"

	"llgen/data"
	"llgen/internal/collect"
	"llgen/internal/config"
)

// LabCorpus aggregates all available text content for one lab.
type LabCorpus struct {
	Lab        data.LabMeta
	Title      string // from playlist metadata
	UploadDate string // YYYYMMDD from playlist metadata

	Transcript string // full plain-text transcript (from VTT)
	GitHubGuide string // markdown from GitHub
	DeckText   string // extracted PPTX slide text
}

// TranscriptExcerpt returns the first n characters of the transcript.
func (c *LabCorpus) TranscriptExcerpt(n int) string {
	if len(c.Transcript) <= n {
		return c.Transcript
	}
	return c.Transcript[:n]
}

// BuildCorpus assembles a LabCorpus for a single lab by reading cached files.
// Missing files are silently skipped (transcript, guide, deck are all optional).
func BuildCorpus(cfg *config.Config, lab data.LabMeta) (*LabCorpus, error) {
	corpus := &LabCorpus{Lab: lab}

	// Load transcript
	transcript, err := loadTranscript(cfg, lab.VideoID)
	if err == nil {
		corpus.Transcript = transcript
	}

	// Load GitHub guide
	if lab.GitHubID != "" {
		guide, err := collect.FetchGitHubGuide(cfg, lab.GitHubID)
		if err == nil {
			corpus.GitHubGuide = guide
		}
	}

	// Load PPTX deck
	if lab.DeckFile != "" && cfg.DecksDir != "" {
		deckPath := filepath.Join(cfg.DecksDir, lab.DeckFile)
		slides, err := collect.ParsePPTX(deckPath)
		if err == nil && len(slides) > 0 {
			corpus.DeckText = collect.SlidesToText(slides)
		}
	}

	return corpus, nil
}

// loadTranscript reads and converts a VTT file to plain text.
// Searches the cache dir in flat layout: <cacheDir>/<videoID>.en.vtt
func loadTranscript(cfg *config.Config, videoID string) (string, error) {
	vttPath := filepath.Join(cfg.CacheDir, videoID+".en.vtt")
	raw, err := os.ReadFile(vttPath)
	if err != nil {
		return "", err
	}
	return VTTToText(string(raw)), nil
}
