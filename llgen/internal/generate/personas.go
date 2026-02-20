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

// personaDefinitions contains the verbatim persona definitions used in all prompts.
const personaDefinitions = `## Persona Definitions

### Persona A — Junior Developer ("Dev")
Early-career engineer (1–3 years experience). Knows Docker, is comfortable
with Python or JavaScript, has heard of CVEs but has never run a scanner.
Security is "someone else's job." Motivation: learn something practical,
get a quick win, and look competent to their team.

**Needs:** Clear success states. Low setup friction. Visual proof that
something is better. The "aha" moment within 15 minutes or they disengage.

---

### Persona B — Platform/DevSecOps Engineer ("Platform")
Mid-senior engineer responsible for container infrastructure, CI/CD pipelines,
and image scanning. Already uses Trivy or Grype. Needs to justify tool
adoption to their team. Skeptical of vendor labs. Motivation: find a
solution to a real problem (CVE noise, compliance requirements, migration
effort).

**Needs:** Concrete CVE numbers they can replicate. Integration examples
(registry config, CI pipeline snippets). Credible before/after data. An
honest discussion of trade-offs.

---

### Persona C — Developer Advocate / Lab Facilitator ("Advocate")
Someone who will deliver this lab to others — a Chainguard DevRel, a
customer's internal champion, or a conference workshop facilitator.
Already knows the material. Motivation: understand what will confuse the
audience, what requires live troubleshooting, and what produces genuine
excitement.

**Needs:** Reliable commands that work in varied environments. Fallback
paths for common failures. High-energy moments that work on screen. A
clear sense of what questions will come up.`

// personaRatingFormat explains the expected output format.
const personaRatingFormat = `## Rating Format

For each lab evaluation, use this format per persona:
**[Persona Label]:** [rating emoji] [2–4 sentences of evaluation]
> "[simulated quote from this persona]"

Rating scale: ✅ Works well · ⚠️ Partial · ❌ Gap`

const personasSystemPrompt = `You are a developer education specialist evaluating the Chainguard Learning Labs series.

Your task is to EVALUATE a specific lab against each of the three personas — not summarize what the lab contains.

For each persona, assess:
- Does the lab meet their specific needs?
- What friction points exist for this persona?
- What moments work particularly well for them?

Rules:
- Do NOT summarize the lab — evaluate how well it serves each persona
- Be specific: reference commands, steps, or content from the lab
- The simulated quote should sound authentic to that persona's voice and concerns
- Note if a lab is particularly well-suited or poorly-suited for a persona`

// Personas generates personas.md using per-lab LLM calls with caching.
func Personas(ctx context.Context, client *claude.Client, cfg *config.Config, labs []data.LabMeta, corpora map[string]*transform.LabCorpus) error {
	if err := os.MkdirAll(cfg.PersonasCacheDir(), 0o755); err != nil {
		return fmt.Errorf("mkdir personas cache: %w", err)
	}

	roster := labRoster(labs)

	// Generate or load per-lab sections
	perLab := make(map[string]string)
	for _, lab := range labs {
		cacheFile := filepath.Join(cfg.PersonasCacheDir(), lab.ID+".md")

		if !cfg.Force {
			if cached, err := os.ReadFile(cacheFile); err == nil {
				perLab[lab.ID] = string(cached)
				fmt.Printf("  personas: %s (cached)\n", lab.ID)
				continue
			}
		}

		fmt.Printf("  personas: generating %s...\n", lab.ID)
		corpus := corpora[lab.ID]
		section, err := generatePersonasSection(ctx, client, lab, corpus, roster)
		if err != nil {
			return fmt.Errorf("personas section %s: %w", lab.ID, err)
		}

		if err := os.WriteFile(cacheFile, []byte(section), 0o644); err != nil {
			return fmt.Errorf("write personas cache %s: %w", cacheFile, err)
		}
		perLab[lab.ID] = section
	}

	// Generate cross-cutting recommendations
	crossCutCacheFile := filepath.Join(cfg.PersonasCacheDir(), "_crosscut.md")
	var crossCutSection string
	if !cfg.Force {
		if cached, err := os.ReadFile(crossCutCacheFile); err == nil {
			crossCutSection = string(cached)
			fmt.Println("  personas: _crosscut (cached)")
		}
	}
	if crossCutSection == "" {
		fmt.Println("  personas: generating _crosscut...")
		var assembled strings.Builder
		for _, lab := range labs {
			assembled.WriteString(perLab[lab.ID])
			assembled.WriteString("\n\n")
		}
		var err error
		crossCutSection, err = generateCrossCutRecommendations(ctx, client, assembled.String())
		if err != nil {
			return fmt.Errorf("cross-cut recommendations: %w", err)
		}
		if err := os.WriteFile(crossCutCacheFile, []byte(crossCutSection), 0o644); err != nil {
			return fmt.Errorf("write crosscut cache: %w", err)
		}
	}

	// Assemble final document
	var doc strings.Builder
	doc.WriteString("# Chainguard Learning Labs — Persona Analysis\n\n")
	doc.WriteString("Three personas evaluated against all 22 labs. Each section covers what that\n")
	doc.WriteString("persona finds valuable, what creates friction, and specific lab ratings.\n\n")
	doc.WriteString("---\n\n")
	doc.WriteString(personaDefinitions)
	doc.WriteString("\n\n---\n\n")
	doc.WriteString(personaRatingFormat)
	doc.WriteString("\n\n---\n\n")
	doc.WriteString("## Lab Ratings by Persona\n\n")
	for _, lab := range labs {
		doc.WriteString(perLab[lab.ID])
		doc.WriteString("\n\n")
	}
	doc.WriteString("---\n\n")
	doc.WriteString(crossCutSection)

	outPath := filepath.Join(cfg.OutputDir, "personas.md")
	if err := os.WriteFile(outPath, []byte(doc.String()), 0o644); err != nil {
		return fmt.Errorf("write %s: %w", outPath, err)
	}
	fmt.Printf("  wrote %s\n", outPath)
	return nil
}

func generatePersonasSection(ctx context.Context, client *claude.Client, lab data.LabMeta, corpus *transform.LabCorpus, roster string) (string, error) {
	var user strings.Builder
	user.WriteString(personaDefinitions)
	user.WriteString("\n\n")
	user.WriteString(personaRatingFormat)
	user.WriteString("\n\n")
	user.WriteString(roster)
	user.WriteString("\n---\n\n")
	user.WriteString(fmt.Sprintf("## Lab being evaluated: %s\n", lab.ID))
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

	user.WriteString(fmt.Sprintf("\nNow evaluate %s against each of the three personas using the format specified.", lab.ID))

	title := lab.ID
	if corpus != nil && corpus.Title != "" {
		title = fmt.Sprintf("%s — %s", lab.ID, corpus.Title)
	}

	text, err := client.Generate(ctx, personasSystemPrompt, user.String(), 2048)
	if err != nil {
		return "", err
	}

	section := fmt.Sprintf("### %s\n\n%s", title, strings.TrimSpace(text))
	return section, nil
}

func generateCrossCutRecommendations(ctx context.Context, client *claude.Client, assembledSections string) (string, error) {
	system := `You are a developer education specialist who has evaluated all 22 Chainguard Learning Labs against three personas.
Based on the per-lab evaluations provided, write a "## Cross-Cutting Persona Recommendations" section.

Include a summary table with columns: Lab ID | Dev | Platform | Advocate
Use the same emoji scale (✅/⚠️/❌) in the table cells.

Then write 2-3 paragraphs of analysis:
- Which persona is best served by the current series?
- Which persona has the most friction and what would most improve their experience?
- Top 3 actionable recommendations for the series as a whole.`

	text, err := client.Generate(ctx, system, "Per-lab persona evaluations:\n\n"+assembledSections, 3000)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(text), nil
}
