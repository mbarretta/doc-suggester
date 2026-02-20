package generate

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"llgen/internal/claude"
	"llgen/internal/config"
)

// hardcodedCaveats contains facts that cannot be derived from transcripts alone.
// These must be injected explicitly into the recommender system prompt.
const hardcodedCaveats = `## Known Issues and Special Notes (inject into recommender)

### ll202510 — JavaScript/CVE Remediation
- **BROKEN**: The auth token step for Chainguard Libraries for JavaScript is broken as of the lab recording. Learners cannot complete the auth flow.
- **MISSING**: The VEX source file referenced in Part 2 is absent from the lab guide.
- **CONFUSING**: Part 2 pivots unexpectedly from JavaScript to Python CVE remediation, confusing learners who came for JS.
- Recommend only for experienced learners who can troubleshoot auth issues independently.

### ll202509 — Static Chainguard Container Images
- **GOLD STANDARD**: Clearest before/after CVE numbers in the series. "Record your results" table. Git branch progression.
- Best lab to recommend for first-time Chainguard users.
- Difficulty: beginner. Suitable for all personas.

### ll202601 — AI with Hardened Containers and Libraries
- **UNPUBLISHED**: Recorded in January 2026 but not yet available on edu.chainguard.dev.
- Video is available at https://www.youtube.com/watch?v=hkoj-dm-5z8
- Recommend only when user explicitly asks about AI/ML security AND lab guides are not required.

### ll202511 — Chainguard OS on Raspberry Pi
- **HARDWARE REQUIRED**: Requires physical Raspberry Pi 5. Cannot be completed in standard dev environment.
- Do not recommend when user asks for labs they can run on their laptop.

### Series notes
- New-format labs (ll202505 and later) have structured guides; old-format labs (pre-ll202505) are video-only.
- Old-format labs have no step-by-step guide; recommend for explorers, not for structured workshops.
- ll202509 is the recommended starting point for almost all personas.`

// Recommender generates recommender-system-prompt.md from the catalog JSON + hardcoded caveats.
func Recommender(ctx context.Context, client *claude.Client, cfg *config.Config) error {
	catalogPath := filepath.Join(cfg.OutputDir, "labs-catalog.json")
	catalogBytes, err := os.ReadFile(catalogPath)
	if err != nil {
		return fmt.Errorf("read labs-catalog.json (run catalog generation first): %w", err)
	}

	system := `You are writing a system prompt for an LLM-powered recommender that helps users find the right Chainguard Learning Lab.

Produce a complete, self-contained system prompt document. The document should:
1. Explain the recommender's purpose and constraints
2. Define matching rules (by topic, difficulty, persona, technology)
3. Specify how to handle edge cases (unpublished labs, broken labs, hardware requirements)
4. Define the response format (brief lab description + direct link + one-line rationale)
5. Include 3 worked examples showing query → recommendation reasoning
6. Embed the catalog notes and known issues

The system prompt should be written in second person ("You are a lab recommender...").
It should be comprehensive enough that an LLM with only this prompt and a user query can give good recommendations.`

	user := fmt.Sprintf("## Labs Catalog (JSON)\n\n```json\n%s\n```\n\n## Known Issues and Caveats\n\n%s\n\nNow write the complete recommender system prompt document.",
		string(catalogBytes), hardcodedCaveats)

	text, err := client.Generate(ctx, system, user, 4096)
	if err != nil {
		return fmt.Errorf("generate recommender: %w", err)
	}

	outPath := filepath.Join(cfg.OutputDir, "recommender-system-prompt.md")
	if err := os.WriteFile(outPath, []byte(text), 0o644); err != nil {
		return fmt.Errorf("write %s: %w", outPath, err)
	}
	fmt.Printf("  wrote %s\n", outPath)
	return nil
}
