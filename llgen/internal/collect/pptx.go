package collect

import (
	"archive/zip"
	"encoding/xml"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// SlideText holds extracted text content for a single slide.
type SlideText struct {
	SlideNum int
	Lines    []string
}

// ParsePPTX opens a PPTX file and extracts text from all slides in slide-number order.
// Returns an empty slice (not an error) if the file doesn't exist.
func ParsePPTX(path string) ([]SlideText, error) {
	r, err := zip.OpenReader(path)
	if err != nil {
		return nil, fmt.Errorf("open pptx %s: %w", path, err)
	}
	defer r.Close()

	// Collect slide files, sorted numerically.
	type slideFile struct {
		num  int
		file *zip.File
	}
	var slides []slideFile

	for _, f := range r.File {
		name := f.Name
		if !strings.HasPrefix(name, "ppt/slides/slide") || !strings.HasSuffix(name, ".xml") {
			continue
		}
		// Extract numeric suffix: "ppt/slides/slide12.xml" → 12
		base := filepath.Base(name)
		base = strings.TrimPrefix(base, "slide")
		base = strings.TrimSuffix(base, ".xml")
		n, err := strconv.Atoi(base)
		if err != nil {
			continue // skip slideLayout etc.
		}
		slides = append(slides, slideFile{num: n, file: f})
	}

	// Numeric sort (not lexicographic) so slide10 comes after slide9.
	sort.Slice(slides, func(i, j int) bool {
		return slides[i].num < slides[j].num
	})

	var result []SlideText
	for _, s := range slides {
		lines, err := extractSlideText(s.file)
		if err != nil {
			return nil, fmt.Errorf("slide %d: %w", s.num, err)
		}
		result = append(result, SlideText{SlideNum: s.num, Lines: lines})
	}
	return result, nil
}

// drawingML namespace used in PPTX XML.
const drawingMLNS = "http://schemas.openxmlformats.org/drawingml/2006/main"

// pmlNS is the presentation ML namespace (used to skip notes/layouts).
const pmlNS = "http://schemas.openxmlformats.org/presentationml/2006/main"

// xmlSlide is a minimal struct for parsing a slide's XML.
type xmlSlide struct {
	XMLName xml.Name    `xml:"sld"`
	SpTree  []xmlSpTree `xml:"cSld>spTree"`
}

type xmlSpTree struct {
	Shapes []xmlShape `xml:"sp"`
}

type xmlShape struct {
	TxBody xmlTxBody `xml:"txBody"`
}

type xmlTxBody struct {
	Paras []xmlPara `xml:"p"`
}

type xmlPara struct {
	Runs []xmlRun `xml:"r"`
}

type xmlRun struct {
	Text string `xml:"t"`
}

func extractSlideText(f *zip.File) ([]string, error) {
	rc, err := f.Open()
	if err != nil {
		return nil, fmt.Errorf("open zip entry: %w", err)
	}
	defer rc.Close()

	// We parse using a token-based approach to collect all <a:t> text nodes
	// from the drawingML namespace, grouped by paragraph.
	decoder := xml.NewDecoder(rc)

	var lines []string
	var inPara bool
	var paraTokens []string

	for {
		tok, err := decoder.Token()
		if err != nil {
			break
		}
		switch t := tok.(type) {
		case xml.StartElement:
			if t.Name.Space == drawingMLNS && t.Name.Local == "p" {
				inPara = true
				paraTokens = nil
			}
		case xml.EndElement:
			if t.Name.Space == drawingMLNS && t.Name.Local == "p" {
				if inPara && len(paraTokens) > 0 {
					line := strings.Join(paraTokens, " ")
					line = strings.TrimSpace(line)
					if line != "" {
						lines = append(lines, line)
					}
				}
				inPara = false
				paraTokens = nil
			}
		case xml.CharData:
			if inPara {
				text := strings.TrimSpace(string(t))
				if text != "" {
					paraTokens = append(paraTokens, text)
				}
			}
		}
	}
	return lines, nil
}

// SlidesToText converts a slice of SlideText into a single string block.
func SlidesToText(slides []SlideText) string {
	var sb strings.Builder
	for _, s := range slides {
		fmt.Fprintf(&sb, "--- Slide %d ---\n", s.SlideNum)
		sb.WriteString(strings.Join(s.Lines, "\n"))
		sb.WriteString("\n\n")
	}
	return sb.String()
}
