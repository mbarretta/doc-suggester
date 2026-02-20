package generate

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"llgen/data"
	"llgen/internal/claude"
	"llgen/internal/collect"
	"llgen/internal/config"
)

// Index generates learning-labs-index.md from lab metadata + playlist info.
// No transcripts or LLM synthesis needed for the index — it is assembled from
// structured metadata, with Claude writing the narrative header and notes.
func Index(ctx context.Context, client *claude.Client, cfg *config.Config, labs []data.LabMeta, playlistInfo map[string]collect.VideoInfo) error {
	// Build a structured description of all labs to pass as input
	var roster strings.Builder
	roster.WriteString("Chainguard Learning Labs — complete lab roster (newest first):\n\n")
	roster.WriteString("| ID | Video ID | Era | Status | DeckFile | GitHubID |\n")
	roster.WriteString("|---|---|---|---|---|---|\n")
	for _, lab := range labs {
		title := ""
		if info, ok := playlistInfo[lab.VideoID]; ok {
			title = info.Title
		}
		inferred := ""
		if lab.IDInferred {
			inferred = " (inferred)"
		}
		deck := lab.DeckFile
		if deck == "" {
			deck = "—"
		}
		github := lab.GitHubID
		if github == "" {
			github = "—"
		}
		roster.WriteString(fmt.Sprintf("| %s%s | %s | %s | %s | %s | %s |\n",
			lab.ID, inferred, lab.VideoID, lab.Era, lab.Status, deck, github,
		))
		if title != "" {
			roster.WriteString(fmt.Sprintf("|   | Title: %s | | | | |\n", title))
		}
	}

	system := `You are a technical writer producing documentation for the Chainguard Learning Labs series.
Generate a well-structured index markdown document for all 22 labs.

The document must include:
1. A brief introduction explaining what Chainguard Learning Labs are
2. A "Two Eras" section explaining old-format (video-only, 14 labs) vs new-format (structured guide + PDF + GitHub, 8+ labs)
3. A summary table with ALL 22 labs (newest first) — columns: ID | Title | Date | Era | Status | Video | Guide | Deck | Repo
4. Per-lab links where available using these URL patterns:
   - Video: https://www.youtube.com/watch?v={videoID}
   - Lab guide: https://edu.chainguard.dev/software-security/learning-labs/{id}/ (new-format only)
   - Slide deck: https://edu.chainguard.dev/downloads/learning-lab-{YYYYMM}.pdf (new-format published only)
   - GitHub: https://github.com/chainguard-dev/edu/tree/main/content/software-security/learning-labs/{id} (when GitHubID is set)
5. A note that ll202601 is recorded but not yet published

Use "—" for unavailable links. ID cells marked "(inferred)" indicate the ID was inferred from the upload date.
Output only the markdown document, no preamble.`

	user := roster.String()

	text, err := client.Generate(ctx, system, user, 4096)
	if err != nil {
		return fmt.Errorf("generate index: %w", err)
	}

	outPath := filepath.Join(cfg.OutputDir, "learning-labs-index.md")
	if err := os.WriteFile(outPath, []byte(text), 0o644); err != nil {
		return fmt.Errorf("write %s: %w", outPath, err)
	}
	fmt.Printf("  wrote %s\n", outPath)
	return nil
}
