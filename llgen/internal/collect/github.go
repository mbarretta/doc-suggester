package collect

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"llgen/internal/config"
)

// FetchGitHubGuide fetches the lab guide markdown from the chainguard-dev/edu GitHub repo.
// URL pattern: https://raw.githubusercontent.com/chainguard-dev/edu/main/content/software-security/learning-labs/{id}.md
//
// Returns ("", nil) gracefully on 404 (old-format labs or ll202601 which has no guide yet).
// Caches result to <cacheDir>/github/<id>.md.
// Skips fetch if cached file exists (unless cfg.Force).
func FetchGitHubGuide(cfg *config.Config, id string) (string, error) {
	cachePath := filepath.Join(cfg.GitHubCacheDir(), id+".md")

	if !cfg.Force {
		if content, err := os.ReadFile(cachePath); err == nil {
			return string(content), nil
		}
	}

	if err := os.MkdirAll(cfg.GitHubCacheDir(), 0o755); err != nil {
		return "", fmt.Errorf("mkdir github cache: %w", err)
	}

	url := "https://raw.githubusercontent.com/chainguard-dev/edu/main/content/software-security/learning-labs/" + id + ".md"
	content, err := fetchWithRetry(url, 2)
	if err != nil {
		return "", err
	}
	if content == "" {
		return "", nil // 404
	}

	if err := os.WriteFile(cachePath, []byte(content), 0o644); err != nil {
		return "", fmt.Errorf("write github cache %s: %w", cachePath, err)
	}
	return content, nil
}

// fetchWithRetry performs an HTTP GET with one retry on network error.
// Returns ("", nil) on 404.
func fetchWithRetry(url string, maxAttempts int) (string, error) {
	var lastErr error
	for attempt := 0; attempt < maxAttempts; attempt++ {
		if attempt > 0 {
			time.Sleep(2 * time.Second)
		}
		content, err := httpGet(url)
		if err == nil {
			return content, nil
		}
		if err == errNotFound {
			return "", nil
		}
		lastErr = err
	}
	return "", lastErr
}

var errNotFound = fmt.Errorf("not found")

func httpGet(url string) (string, error) {
	resp, err := http.Get(url) //nolint:gosec // URL is constructed from trusted data
	if err != nil {
		return "", fmt.Errorf("http get %s: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return "", errNotFound
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("http get %s: status %d", url, resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read body %s: %w", url, err)
	}
	return string(body), nil
}
