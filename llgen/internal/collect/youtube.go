package collect

import (
	"bufio"
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"llgen/data"
	"llgen/internal/config"
)

// VideoInfo holds metadata fetched from the YouTube playlist.
type VideoInfo struct {
	Title      string
	UploadDate string // YYYYMMDD
}

// FetchPlaylistInfo calls yt-dlp to list playlist metadata without downloading anything.
// Returns a map of videoID → VideoInfo. Non-fatal on yt-dlp failure.
func FetchPlaylistInfo(cfg *config.Config) (map[string]VideoInfo, error) {
	if err := checkYtDlp(cfg.YtDlpPath); err != nil {
		return nil, err
	}

	cmd := exec.Command(cfg.YtDlpPath,
		"--flat-playlist",
		"--print", "%(id)s\t%(title)s\t%(upload_date)s",
		data.PlaylistURL,
	)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("yt-dlp playlist fetch: %w", err)
	}

	result := make(map[string]VideoInfo)
	scanner := bufio.NewScanner(bytes.NewReader(out))
	for scanner.Scan() {
		line := scanner.Text()
		parts := strings.SplitN(line, "\t", 3)
		if len(parts) != 3 {
			continue
		}
		id, title, date := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1]), strings.TrimSpace(parts[2])
		if id == "" {
			continue
		}
		result[id] = VideoInfo{Title: title, UploadDate: date}
	}
	return result, scanner.Err()
}

// DownloadTranscript downloads the auto-generated English VTT transcript for a lab's video.
// Skips download if the VTT file already exists (unless cfg.Force).
// Also downloads the video description file (--write-description).
//
// Output files are written directly to cfg.CacheDir (flat layout):
//
//	<cacheDir>/<videoID>.en.vtt
//	<cacheDir>/<videoID>.description
func DownloadTranscript(cfg *config.Config, lab data.LabMeta) error {
	vttPath := filepath.Join(cfg.CacheDir, lab.VideoID+".en.vtt")
	if !cfg.Force {
		if _, err := os.Stat(vttPath); err == nil {
			return nil // already cached
		}
	}

	if err := checkYtDlp(cfg.YtDlpPath); err != nil {
		return err
	}

	if err := os.MkdirAll(cfg.CacheDir, 0o755); err != nil {
		return fmt.Errorf("mkdir %s: %w", cfg.CacheDir, err)
	}

	cmd := exec.Command(cfg.YtDlpPath,
		"--write-auto-sub",
		"--sub-lang", "en",
		"--sub-format", "vtt",
		"--write-description",
		"--no-download",
		"-o", "%(id)s",
		"--paths", cfg.CacheDir,
		"https://www.youtube.com/watch?v="+lab.VideoID,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("yt-dlp transcript %s: %w", lab.VideoID, err)
	}
	return nil
}

func checkYtDlp(path string) error {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return fmt.Errorf("yt-dlp not found at %s — install with: brew install yt-dlp", path)
	}
	return nil
}
