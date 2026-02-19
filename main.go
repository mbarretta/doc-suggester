package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/PuerkitoBio/goquery"
	md "github.com/JohannesKaufmann/html-to-markdown"
)

const (
	baseURL        = "https://chainguard.dev"
	unchainedURL   = baseURL + "/unchained"
	outputDir      = "output"
	archivePath    = outputDir + "/unchained-archive.md"
	checkpointPath = outputDir + "/checkpoint.json"
	workers        = 10
	userAgent      = "Mozilla/5.0 (compatible; BlogScraper/1.0)"
)

var (
	httpClient = &http.Client{Timeout: 30 * time.Second}
	// Pass empty domain — html-to-markdown v1 mangles full URLs with scheme.
	// Relative links stay relative; boilerplate cleanup handles them.
	mdConverter = md.NewConverter("", true, nil)

	// Precompiled cleanup regexes
	reBreadcrumb   = regexp.MustCompile(`(?m)^\[All Articles\]\(/unchained\)\n+`)
	reDateLine     = regexp.MustCompile(`(?m)^(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}\n+`)
	reShareFooter  = regexp.MustCompile(`(?s)\nShare this article.*$`)
	reRelated      = regexp.MustCompile(`(?s)\nRelated articles\n.*$`)
	reWantMore     = regexp.MustCompile(`(?s)\n## Want to learn more about Chainguard\?.*$`)
	reCGCta        = regexp.MustCompile(`(?s)\nChainguard provides a secure foundation.*?\[Get in touch\][^\n]*\n`)
	reReadyStart   = regexp.MustCompile(`\n_Ready to get started[^\n]*\n`)
	reNextImage    = regexp.MustCompile(`(?m)^!\[\]\(/_next/image\?url=[^\n]*\)\n`)
	reExcessBlanks = regexp.MustCompile(`\n{3,}`)

	reDateText = regexp.MustCompile(`^(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}$`)
)

// ─── Types ───────────────────────────────────────────────────────────────────

type blogPost struct {
	Title string
	URL   string
	Slug  string
}

type checkpointEntry struct {
	Title     string `json:"title"`
	URL       string `json:"url"`
	Date      string `json:"date"`
	ScrapedAt string `json:"scraped_at"`
}

type checkpoint map[string]checkpointEntry

type scrapeResult struct {
	slug     string
	title    string
	url      string
	date     string
	markdown string
	err      error
}

// ─── HTTP ────────────────────────────────────────────────────────────────────

func fetchPage(url string) (string, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", userAgent)
	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	return string(body), err
}

// ─── Listing ─────────────────────────────────────────────────────────────────

func getAllBlogLinks() ([]blogPost, error) {
	var posts []blogPost
	seen := make(map[string]bool)
	fmt.Println("Fetching blog listing pages...")

	for page := 1; ; page++ {
		url := unchainedURL
		if page > 1 {
			url = fmt.Sprintf("%s?page=%d", unchainedURL, page)
		}
		fmt.Printf("  Fetching page %d...\n", page)

		html, err := fetchPage(url)
		if err != nil {
			return posts, fmt.Errorf("page %d: %w", page, err)
		}
		doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
		if err != nil {
			return posts, err
		}

		doc.Find(`a[href^="/unchained/"]`).Each(func(_ int, s *goquery.Selection) {
			href, _ := s.Attr("href")
			if href == "/unchained" || strings.Contains(href, "/category/") {
				return
			}
			slug := strings.TrimPrefix(href, "/unchained/")
			if slug == "" || strings.Contains(slug, "?") || seen[slug] {
				return
			}
			seen[slug] = true
			title := strings.TrimSpace(s.Text())
			if title == "" {
				title = slug
			}
			posts = append(posts, blogPost{Title: title, URL: baseURL + href, Slug: slug})
		})

		btn := doc.Find(`button[aria-label="Go to next page"]`)
		if btn.Length() == 0 {
			break
		}
		if _, disabled := btn.Attr("disabled"); disabled {
			break
		}
	}

	fmt.Printf("Found %d blog posts.\n", len(posts))
	return posts, nil
}

// ─── Scraping ────────────────────────────────────────────────────────────────

var articleSelectors = []string{
	"article", ".post-content", ".blog-content", ".article-content", "main", `[role="main"]`,
}

func downloadAndConvertPost(post blogPost) scrapeResult {
	html, err := fetchPage(post.URL)
	if err != nil {
		return scrapeResult{slug: post.Slug, err: err}
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return scrapeResult{slug: post.Slug, err: err}
	}

	title := post.Title
	if h1 := strings.TrimSpace(doc.Find("h1").First().Text()); h1 != "" {
		title = h1
	}

	var contentHTML string
	for _, sel := range articleSelectors {
		el := doc.Find(sel)
		if el.Length() == 0 {
			continue
		}
		el.Find("nav, header, footer, script, style").Remove()
		h, _ := el.Html()
		if len(h) > 100 {
			contentHTML = h
			break
		}
	}
	if contentHTML == "" {
		body := doc.Find("body")
		body.Find("nav, header, footer, script, style").Remove()
		contentHTML, _ = body.Html()
	}

	// Extract publish date: prefer <time datetime="..."> in ISO format,
	// then <time> text, then scan paragraphs for "Month DD, YYYY".
	date := ""
	if t := doc.Find("time").First(); t.Length() > 0 {
		if dt, ok := t.Attr("datetime"); ok && dt != "" {
			if parsed, parseErr := time.Parse("2006-01-02", dt); parseErr == nil {
				date = parsed.Format("January 2, 2006")
			} else {
				date = dt
			}
		} else {
			date = strings.TrimSpace(t.Text())
		}
	}
	if date == "" {
		doc.Find("p, div, span").EachWithBreak(func(_ int, s *goquery.Selection) bool {
			if text := strings.TrimSpace(s.Text()); reDateText.MatchString(text) {
				date = text
				return false
			}
			return true
		})
	}

	rawMD, err := mdConverter.ConvertString(contentHTML)
	if err != nil {
		return scrapeResult{slug: post.Slug, err: err}
	}
	return scrapeResult{
		slug:     post.Slug,
		title:    title,
		url:      post.URL,
		date:     date,
		markdown: cleanMarkdown(rawMD, title),
	}
}

func scrapeAll(posts []blogPost) map[string]scrapeResult {
	out := make(map[string]scrapeResult, len(posts))
	ch := make(chan scrapeResult, len(posts))
	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	var completed atomic.Int32

	for _, post := range posts {
		wg.Add(1)
		sem <- struct{}{}
		go func(p blogPost) {
			defer wg.Done()
			defer func() { <-sem }()
			r := downloadAndConvertPost(p)
			n := int(completed.Add(1))
			if r.err != nil {
				fmt.Printf("  [%d/%d] ERROR %s: %v\n", n, len(posts), p.Slug, r.err)
			} else {
				fmt.Printf("  [%d/%d] %s\n", n, len(posts), p.Slug)
			}
			ch <- r
		}(post)
	}

	go func() {
		wg.Wait()
		close(ch)
	}()

	for r := range ch {
		if r.err == nil {
			out[r.slug] = r
		}
	}
	return out
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

func cleanMarkdown(raw, title string) string {
	s := raw
	s = reBreadcrumb.ReplaceAllString(s, "")
	s = reDateLine.ReplaceAllString(s, "")

	// Remove duplicate H1 (title already appears as H2 in the combined file)
	reH1 := regexp.MustCompile(`(?m)^# ` + regexp.QuoteMeta(title) + `\s*\n+`)
	s = reH1.ReplaceAllString(s, "")

	s = reShareFooter.ReplaceAllString(s, "")
	s = reRelated.ReplaceAllString(s, "")
	s = reWantMore.ReplaceAllString(s, "")
	s = reCGCta.ReplaceAllString(s, "")
	s = reReadyStart.ReplaceAllString(s, "")
	s = reNextImage.ReplaceAllString(s, "")
	s = reExcessBlanks.ReplaceAllString(s, "\n\n")
	return strings.TrimSpace(s)
}

// ─── Output ──────────────────────────────────────────────────────────────────

func formatPost(r scrapeResult) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("## %s\n\n", r.title))
	if r.date != "" {
		sb.WriteString(fmt.Sprintf("*Source: %s | %s*\n\n", r.url, r.date))
	} else {
		sb.WriteString(fmt.Sprintf("*Source: %s*\n\n", r.url))
	}
	sb.WriteString(r.markdown)
	sb.WriteString("\n\n---\n\n")
	return sb.String()
}

// ─── Checkpoint ──────────────────────────────────────────────────────────────

func loadCheckpoint() checkpoint {
	cp := make(checkpoint)
	data, err := os.ReadFile(checkpointPath)
	if err != nil {
		if !os.IsNotExist(err) {
			log.Printf("Warning: could not read checkpoint: %v", err)
		}
		return cp
	}
	if err := json.Unmarshal(data, &cp); err != nil {
		log.Printf("Warning: could not parse checkpoint: %v", err)
	}
	return cp
}

func saveCheckpoint(cp checkpoint) {
	data, _ := json.MarshalIndent(cp, "", "  ")
	if err := os.WriteFile(checkpointPath, data, 0644); err != nil {
		log.Printf("Warning: could not save checkpoint: %v", err)
	}
}

// ─── Main ────────────────────────────────────────────────────────────────────

func main() {
	force := flag.Bool("force", false, "re-scrape all posts and rebuild the archive from scratch")
	flag.Parse()

	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		log.Fatalf("mkdir: %v", err)
	}

	cp := loadCheckpoint()

	allPosts, err := getAllBlogLinks()
	if err != nil {
		log.Fatalf("listing: %v", err)
	}
	if len(allPosts) == 0 {
		log.Fatal("no posts found")
	}

	// On -force, ignore the checkpoint and scrape everything.
	// Otherwise, only scrape slugs not yet in the checkpoint.
	var toScrape []blogPost
	if *force {
		toScrape = allPosts
		cp = make(checkpoint)
		fmt.Printf("\nForce mode: re-scraping all %d posts.\n", len(toScrape))
	} else {
		for _, p := range allPosts {
			if _, ok := cp[p.Slug]; !ok {
				toScrape = append(toScrape, p)
			}
		}
	}

	if len(toScrape) == 0 {
		fmt.Println("All posts up to date.")
		return
	}

	if !*force {
		fmt.Printf("\nScraping %d new posts (%d already cached)...\n",
			len(toScrape), len(allPosts)-len(toScrape))
	}

	scraped := scrapeAll(toScrape)

	// Update checkpoint with newly scraped posts.
	now := time.Now().UTC().Format(time.RFC3339)
	for slug, r := range scraped {
		cp[slug] = checkpointEntry{
			Title:     r.title,
			URL:       r.url,
			Date:      r.date,
			ScrapedAt: now,
		}
	}
	saveCheckpoint(cp)

	// Write output.
	// -force or no existing archive: rebuild the full file in listing order.
	// Incremental: append new posts in listing order.
	_, archiveErr := os.Stat(archivePath)
	rebuild := *force || os.IsNotExist(archiveErr)

	if rebuild {
		f, err := os.Create(archivePath)
		if err != nil {
			log.Fatalf("create archive: %v", err)
		}
		defer f.Close()
		f.WriteString("# Unchained Blog Archive\n\n")
		f.WriteString("*Articles from [chainguard.dev/unchained](https://chainguard.dev/unchained)*\n\n")
		f.WriteString("---\n\n")
		n := 0
		for _, p := range allPosts {
			if r, ok := scraped[p.Slug]; ok {
				f.WriteString(formatPost(r))
				n++
			}
		}
		fmt.Printf("\nDone! Archive rebuilt with %d posts: %s\n", n, archivePath)
	} else {
		f, err := os.OpenFile(archivePath, os.O_APPEND|os.O_WRONLY, 0644)
		if err != nil {
			log.Fatalf("open archive: %v", err)
		}
		defer f.Close()
		n := 0
		for _, p := range allPosts {
			if r, ok := scraped[p.Slug]; ok {
				f.WriteString(formatPost(r))
				n++
			}
		}
		fmt.Printf("\nDone! %d new posts appended to %s\n", n, archivePath)
	}
}
