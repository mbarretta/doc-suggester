package transform

import (
	"bufio"
	"regexp"
	"strings"
)

var (
	// inlineTagRe strips inline word-timing tags like <00:00:01.520><c> word</c>
	inlineTagRe = regexp.MustCompile(`<[^>]+>`)
	// timestampLineRe matches VTT timestamp lines: "00:00:01.520 --> 00:00:04.000"
	timestampLineRe = regexp.MustCompile(`^\d+:\d+`)
)

// VTTToText converts a YouTube auto-generated VTT transcript to clean prose.
//
// YouTube VTT has two challenges handled here:
//  1. Inline word-timing tags (stripped with inlineTagRe)
//  2. Rolling duplicates: each cue emits the previous sentence before adding
//     new words. Deduplicated by checking if line[n] is a prefix of line[n+1].
func VTTToText(vttContent string) string {
	var lines []string
	scanner := bufio.NewScanner(strings.NewReader(vttContent))
	for scanner.Scan() {
		raw := scanner.Text()

		// Strip inline timing/styling tags
		cleaned := inlineTagRe.ReplaceAllString(raw, "")
		cleaned = strings.TrimSpace(cleaned)

		// Skip structural lines
		if cleaned == "" ||
			cleaned == "WEBVTT" ||
			strings.HasPrefix(cleaned, "Kind:") ||
			strings.HasPrefix(cleaned, "Language:") ||
			timestampLineRe.MatchString(cleaned) ||
			isNumeric(cleaned) {
			continue
		}

		lines = append(lines, cleaned)
	}

	// Deduplicate rolling prefixes:
	// If lines[i] is a prefix of lines[i+1], skip lines[i].
	var deduped []string
	for i, line := range lines {
		if i+1 < len(lines) && strings.HasPrefix(lines[i+1], line) {
			continue
		}
		deduped = append(deduped, line)
	}

	return strings.Join(deduped, " ")
}

func isNumeric(s string) bool {
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return len(s) > 0
}
