package generate

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"llgen/data"
	"llgen/internal/claude"
	"llgen/internal/config"
	"llgen/internal/transform"
)

const improvementsSystemPrompt = `You are a senior developer educator reviewing the Chainguard Learning Labs series.

Your task is to write ANALYTICAL IMPROVEMENT SUGGESTIONS for a specific lab — not a summary of what the lab contains.

Use these three sub-sections (use #### headings):
#### Value Demonstration
How well does the lab show concrete, measurable value? Are CVE numbers clearly before/after? Is there a "wow" moment?

#### Clarity
Is the lab guide clear? Are commands copy-paste ready? Are prerequisites stated upfront? Where will learners get stuck?

#### Simplification / Wow
What could be cut to reduce friction? What small change would produce the biggest improvement in engagement or retention?

Rules:
- Reference specific content from the lab (commands, steps, numbers) to ground your critiques
- Do NOT summarize what the lab does — evaluate what it does well or poorly
- Be specific and actionable. "Add a before/after CVE table" is better than "improve clarity"
- Note cross-lab connections where relevant (e.g. "this lab pairs well with ll202509")`

// labRoster returns a one-line-per-lab string listing all labs for cross-lab awareness.
func labRoster(labs []data.LabMeta) string {
	var sb strings.Builder
	sb.WriteString("Full lab roster (for cross-lab references):\n")
	for _, l := range labs {
		sb.WriteString(fmt.Sprintf("- %s (%s)\n", l.ID, l.Era))
	}
	return sb.String()
}

// Improvements generates improvements.md using per-lab LLM calls with caching.
func Improvements(ctx context.Context, client *claude.Client, cfg *config.Config, labs []data.LabMeta, corpora map[string]*transform.LabCorpus) error {
	if err := os.MkdirAll(cfg.ImprovementsCacheDir(), 0o755); err != nil {
		return fmt.Errorf("mkdir improvements cache: %w", err)
	}

	roster := labRoster(labs)

	// Generate or load per-lab sections
	perLab := make(map[string]string)
	for _, lab := range labs {
		cacheFile := filepath.Join(cfg.ImprovementsCacheDir(), lab.ID+".md")

		if !cfg.Force {
			if cached, err := os.ReadFile(cacheFile); err == nil {
				perLab[lab.ID] = string(cached)
				fmt.Printf("  improvements: %s (cached)\n", lab.ID)
				continue
			}
		}

		fmt.Printf("  improvements: generating %s...\n", lab.ID)
		corpus := corpora[lab.ID]
		section, err := generateImprovementsSection(ctx, client, lab, corpus, roster)
		if err != nil {
			return fmt.Errorf("improvements section %s: %w", lab.ID, err)
		}

		if err := os.WriteFile(cacheFile, []byte(section), 0o644); err != nil {
			return fmt.Errorf("write improvements cache %s: %w", cacheFile, err)
		}
		perLab[lab.ID] = section
	}

	// Generate series-level observations
	seriesCacheFile := filepath.Join(cfg.ImprovementsCacheDir(), "_series.md")
	var seriesSection string
	if !cfg.Force {
		if cached, err := os.ReadFile(seriesCacheFile); err == nil {
			seriesSection = string(cached)
			fmt.Println("  improvements: _series (cached)")
		}
	}
	if seriesSection == "" {
		fmt.Println("  improvements: generating _series...")
		var assembled strings.Builder
		for _, lab := range labs {
			assembled.WriteString(perLab[lab.ID])
			assembled.WriteString("\n\n")
		}
		var err error
		seriesSection, err = generateSeriesObservations(ctx, client, assembled.String())
		if err != nil {
			return fmt.Errorf("series observations: %w", err)
		}
		if err := os.WriteFile(seriesCacheFile, []byte(seriesSection), 0o644); err != nil {
			return fmt.Errorf("write series cache: %w", err)
		}
	}

	// Assemble final document
	var doc strings.Builder
	doc.WriteString("# Chainguard Learning Labs — Improvement Analysis\n\n")
	doc.WriteString(seriesSection)
	doc.WriteString("\n\n---\n\n## Per-Lab Analysis\n\n")
	for _, lab := range labs {
		doc.WriteString(perLab[lab.ID])
		doc.WriteString("\n\n")
	}

	outPath := filepath.Join(cfg.OutputDir, "improvements.md")
	if err := os.WriteFile(outPath, []byte(doc.String()), 0o644); err != nil {
		return fmt.Errorf("write %s: %w", outPath, err)
	}
	fmt.Printf("  wrote %s\n", outPath)
	return nil
}

func generateImprovementsSection(ctx context.Context, client *claude.Client, lab data.LabMeta, corpus *transform.LabCorpus, roster string) (string, error) {
	var user strings.Builder
	user.WriteString(roster)
	user.WriteString("\n---\n\n")
	user.WriteString(fmt.Sprintf("## Lab being analyzed: %s\n", lab.ID))
	user.WriteString(fmt.Sprintf("Era: %s | Status: %s\n\n", lab.Era, lab.Status))

	if corpus != nil {
		if corpus.Title != "" {
			user.WriteString(fmt.Sprintf("Title: %s\n\n", corpus.Title))
		}
		if corpus.Transcript != "" {
			user.WriteString("### Full Transcript:\n")
			user.WriteString(corpus.Transcript)
			user.WriteString("\n\n")
		}
		if corpus.GitHubGuide != "" {
			user.WriteString("### GitHub Lab Guide:\n")
			user.WriteString(corpus.GitHubGuide)
			user.WriteString("\n\n")
		}
		if corpus.DeckText != "" {
			user.WriteString("### Slide Deck:\n")
			user.WriteString(corpus.DeckText)
			user.WriteString("\n\n")
		}
	}

	user.WriteString(fmt.Sprintf("\nNow write the improvement analysis for %s using the three sub-sections specified.", lab.ID))

	title := lab.ID
	if corpus != nil && corpus.Title != "" {
		title = fmt.Sprintf("%s — %s", lab.ID, corpus.Title)
	}

	text, err := client.Generate(ctx, improvementsSystemPrompt, user.String(), 4096)
	if err != nil {
		return "", err
	}

	// Wrap in a section header
	section := fmt.Sprintf("### %s\n\n%s", title, strings.TrimSpace(text))
	return section, nil
}

func generateSeriesObservations(ctx context.Context, client *claude.Client, assembledSections string) (string, error) {
	system := `You are a senior developer educator who has just reviewed all 22 Chainguard Learning Labs.
Based on the per-lab analyses provided, write a "## Series-Level Observations" section.

Include:
- 3-5 cross-cutting strengths of the series
- 3-5 cross-cutting weaknesses or gaps
- Top 3 highest-priority improvements that would have the most impact across the series
- Any patterns in what consistently works or consistently fails

Be analytical and specific. Reference lab IDs where relevant.`

	text, err := client.Generate(ctx, system, "Per-lab analyses:\n\n"+assembledSections, 4096)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(text), nil
}
