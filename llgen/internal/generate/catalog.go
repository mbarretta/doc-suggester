package generate

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"llgen/data"
	"llgen/internal/claude"
	"llgen/internal/config"
	"llgen/internal/transform"
)

// catalogSchema describes the JSON fields expected in each lab entry.
const catalogSchema = `{
  "id": "string — lab ID e.g. ll202509",
  "id_note": "string or null — notes about inferred/unpublished IDs",
  "title": "string — full title from video/guide",
  "date": "string — YYYY-MM format",
  "era": "string — 'new-format' or 'old-format'",
  "status": "string — 'published' or 'recorded, not yet published'",
  "instructor": "string — presenter name(s)",
  "recording_url": "string — https://www.youtube.com/watch?v={videoID}",
  "lab_page_url": "string or null — https://edu.chainguard.dev/.../learning-labs/{id}/ for new-format published",
  "deck_public_url": "string or null — https://edu.chainguard.dev/downloads/learning-lab-YYYYMM.pdf for new-format published",
  "github_repos": ["array of repo URLs mentioned in the lab"],
  "technologies": ["array of tech/tools used in the lab"],
  "chainguard_products": ["array of Chainguard products demonstrated"],
  "difficulty": "string — 'beginner', 'intermediate', or 'advanced'",
  "prerequisites": ["array of prerequisite skills or tools"],
  "what_you_build": "string — one sentence describing the concrete artifact or outcome",
  "problems_addressed": ["array of 2-4 specific problems this lab solves"],
  "summary": "string — 2-4 sentence description of the lab content and value",
  "personas": ["array of audience types this lab serves best"],
  "intent_signals": ["array of 8-15 search queries or keywords that should route to this lab"],
  "related_labs": ["array of lab IDs most closely related by topic"]
}`

// referenceEntry is a concrete example (ll202509) shown to Claude for few-shot guidance.
const referenceEntry = `{
  "id": "ll202509",
  "id_note": null,
  "title": "Static Chainguard Container Images",
  "date": "2025-09",
  "era": "new-format",
  "status": "published",
  "instructor": "Erika Heidi",
  "recording_url": "https://www.youtube.com/watch?v=4Cjy_iBNr3I",
  "lab_page_url": "https://edu.chainguard.dev/software-security/learning-labs/ll202509/",
  "deck_public_url": null,
  "github_repos": ["https://github.com/chainguard-demo/ll202509"],
  "technologies": ["Docker", "grype"],
  "chainguard_products": ["Chainguard Containers (static images)"],
  "difficulty": "beginner",
  "prerequisites": ["Docker"],
  "what_you_build": "A multi-stage Dockerfile that produces a zero-CVE static binary container image, with before/after CVE counts measured by grype.",
  "problems_addressed": [
    "High CVE counts in standard base images",
    "Runtime attack surface from shells and package managers in containers",
    "Difficulty justifying image hardening investment without concrete numbers"
  ],
  "summary": "Demonstrates how to migrate from a standard base image to a Chainguard static image for a compiled binary. Uses grype to measure CVE count before and after migration. Includes a 'record your results' table and Git branch progression that makes it easy to see the delta. The gold-standard lab in the series for clarity of outcome.",
  "personas": ["junior developer", "platform engineer", "DevSecOps", "developer advocate"],
  "intent_signals": [
    "static container images", "zero CVE container", "distroless", "scratch image", "grype scan",
    "reduce container CVEs", "minimal base image", "container hardening", "Chainguard static",
    "multi-stage Dockerfile", "binary-only container", "secure container images"
  ],
  "related_labs": ["ll202508", "ll202512"]
}`

// Catalog generates labs-catalog.json using per-lab LLM calls with caching.
func Catalog(ctx context.Context, client *claude.Client, cfg *config.Config, labs []data.LabMeta, corpora map[string]*transform.LabCorpus) error {
	if err := os.MkdirAll(cfg.CatalogCacheDir(), 0o755); err != nil {
		return fmt.Errorf("mkdir catalog cache: %w", err)
	}

	var entries []json.RawMessage

	for _, lab := range labs {
		cacheFile := filepath.Join(cfg.CatalogCacheDir(), lab.ID+".json")

		// Use cache unless forced
		if !cfg.Force {
			if cached, err := os.ReadFile(cacheFile); err == nil {
				if json.Valid(cached) {
					entries = append(entries, json.RawMessage(cached))
					fmt.Printf("  catalog: %s (cached)\n", lab.ID)
					continue
				}
			}
		}

		fmt.Printf("  catalog: generating %s...\n", lab.ID)
		corpus := corpora[lab.ID]
		entry, err := generateCatalogEntry(ctx, client, lab, corpus)
		if err != nil {
			return fmt.Errorf("catalog entry %s: %w", lab.ID, err)
		}

		// Write to cache
		if err := os.WriteFile(cacheFile, []byte(entry), 0o644); err != nil {
			return fmt.Errorf("write catalog cache %s: %w", cacheFile, err)
		}
		entries = append(entries, json.RawMessage(entry))
	}

	// Assemble final JSON
	catalog := struct {
		Description string            `json:"description"`
		Labs        []json.RawMessage `json:"labs"`
	}{
		Description: "Chainguard Learning Labs catalog. 22 labs total across two eras. New-format labs (ll202505+) have a written lab guide, PDF deck, and GitHub demo repo. Old-format labs (pre-ll202505) are video-only.",
		Labs:        entries,
	}

	out, err := json.MarshalIndent(catalog, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal catalog: %w", err)
	}

	outPath := filepath.Join(cfg.OutputDir, "labs-catalog.json")
	if err := os.WriteFile(outPath, out, 0o644); err != nil {
		return fmt.Errorf("write %s: %w", outPath, err)
	}
	fmt.Printf("  wrote %s\n", outPath)
	return nil
}

func generateCatalogEntry(ctx context.Context, client *claude.Client, lab data.LabMeta, corpus *transform.LabCorpus) (string, error) {
	system := fmt.Sprintf(`You are building a structured catalog of the Chainguard Learning Labs series.

For the lab described below, output ONLY a valid JSON object matching this schema:
%s

Rules:
- Output raw JSON only. No markdown fences. No prose. No array wrapper.
- Use null (not "") for unavailable string fields.
- Use [] for empty arrays.
- The "recording_url" is always https://www.youtube.com/watch?v={videoID}
- Set "lab_page_url" to https://edu.chainguard.dev/software-security/learning-labs/{id}/ for new-format published labs; null otherwise.
- Set "deck_public_url" to https://edu.chainguard.dev/downloads/learning-lab-YYYYMM.pdf for new-format published labs that have a deck; null otherwise.
- "intent_signals" should contain 8-15 specific search queries that would indicate a user wants this lab.
- "related_labs" should list 2-4 IDs of the most topically similar labs from the series.

Here is a complete reference example for ll202509:
%s`, catalogSchema, referenceEntry)

	var inputParts []string
	inputParts = append(inputParts, fmt.Sprintf("## Lab: %s\n", lab.ID))
	inputParts = append(inputParts, fmt.Sprintf("- VideoID: %s\n- Era: %s\n- Status: %s\n- IDInferred: %v\n- DeckFile: %s\n- GitHubID: %s\n",
		lab.VideoID, lab.Era, lab.Status, lab.IDInferred, lab.DeckFile, lab.GitHubID))

	if corpus != nil {
		if corpus.Title != "" {
			inputParts = append(inputParts, fmt.Sprintf("- Title (from playlist): %s\n", corpus.Title))
		}
		if corpus.Transcript != "" {
			inputParts = append(inputParts, fmt.Sprintf("\n### Transcript (first 3000 chars):\n%s\n", corpus.TranscriptExcerpt(3000)))
		}
		if corpus.GitHubGuide != "" {
			inputParts = append(inputParts, fmt.Sprintf("\n### GitHub Lab Guide:\n%s\n", corpus.GitHubGuide))
		}
		if corpus.DeckText != "" {
			inputParts = append(inputParts, fmt.Sprintf("\n### Slide Deck Text:\n%s\n", corpus.DeckText))
		}
	}

	user := strings.Join(inputParts, "")

	// Use extended thinking for better cross-lab reasoning
	var text string
	var err error
	text, err = client.GenerateWithThinking(ctx, system, user, 2048, 4000)
	if err != nil {
		// Fall back to standard generation if extended thinking fails
		text, err = client.Generate(ctx, system, user, 2048)
		if err != nil {
			return "", err
		}
	}

	// Strip any accidental markdown fences
	text = stripFences(text)

	// Validate JSON
	var raw json.RawMessage
	if err := json.Unmarshal([]byte(text), &raw); err != nil {
		// Retry once without extended thinking
		text2, err2 := client.Generate(ctx, system, user+" OUTPUT JSON ONLY. NO FENCES.", 2048)
		if err2 != nil {
			return "", fmt.Errorf("invalid JSON and retry failed: original=%v retry=%v", err, err2)
		}
		text2 = stripFences(text2)
		if err3 := json.Unmarshal([]byte(text2), &raw); err3 != nil {
			return "", fmt.Errorf("invalid JSON after retry: %v\nraw: %s", err3, text2[:min(200, len(text2))])
		}
		return text2, nil
	}

	return text, nil
}

func stripFences(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```") {
		lines := strings.SplitN(s, "\n", 2)
		if len(lines) == 2 {
			s = lines[1]
		}
	}
	if strings.HasSuffix(s, "```") {
		s = s[:strings.LastIndex(s, "```")]
	}
	return strings.TrimSpace(s)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
