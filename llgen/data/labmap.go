package data

// LabMeta holds static metadata for one Learning Lab.
// This mapping cannot be derived dynamically; it is hardcoded here.
type LabMeta struct {
	ID         string // e.g. "ll202509"
	IDInferred bool   // true for old-format labs where ID is inferred from upload date
	VideoID    string // YouTube video ID
	DeckFile   string // filename in DecksDir, or ""
	GitHubID   string // same as ID if in GitHub repo, else ""
	Era        string // "new-format" | "old-format"
	Status     string // "published" | "recorded, not yet published"
}

// Labs is the authoritative ordered list of all Learning Labs, newest first.
// Playlist ordering from yt-dlp is ignored; this slice is the source of truth.
var Labs = []LabMeta{
	{
		ID:         "ll202601",
		IDInferred: true,
		VideoID:    "hkoj-dm-5z8",
		DeckFile:   "AI Learning Lab (January 2026).pptx",
		GitHubID:   "",
		Era:        "new-format",
		Status:     "recorded, not yet published",
	},
	{
		ID:       "ll202512",
		VideoID:  "z5SNwBC4T-Q",
		DeckFile: "Dev Rel_ Learning Lab_ Shipping Safer Container Runtimes in 2026.pptx",
		GitHubID: "ll202512",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202511",
		VideoID:  "SvUU2n2mQ7M",
		DeckFile: "Dev Rel_ Learning Lab_ Chainguard OS on Raspberry Pi.pptx",
		GitHubID: "ll202511",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202510",
		VideoID:  "6V7IHtYekwM",
		DeckFile: "",
		GitHubID: "ll202510",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202509",
		VideoID:  "4Cjy_iBNr3I",
		DeckFile: "",
		GitHubID: "ll202509",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202508",
		VideoID:  "HzZRFpnKKIU",
		DeckFile: "Dev Rel_ Learning Lab_ Dockerfile Converter.pptx",
		GitHubID: "ll202508",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202507",
		VideoID:  "JGSc6BwjbRI",
		DeckFile: "Dev Rel_ Learning Lab_ AI Images (July 2025).pptx",
		GitHubID: "ll202507",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202506",
		VideoID:  "h_nzhPY_vDA",
		DeckFile: "Dev Rel_ Learning Lab_ Python Libraries.pptx",
		GitHubID: "ll202506",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:       "ll202505",
		VideoID:  "z42b2_lePNI",
		DeckFile: "",
		GitHubID: "ll202505",
		Era:      "new-format",
		Status:   "published",
	},
	{
		ID:         "ll202503",
		IDInferred: true,
		VideoID:    "q6I0JC3h06U",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202502",
		IDInferred: true,
		VideoID:    "922G7SLs0b0",
		DeckFile:   "Dev Rel_ Learning Lab_ Python.pptx",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202501",
		IDInferred: true,
		VideoID:    "YAo7Bp6S4bY",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202412",
		IDInferred: true,
		VideoID:    "SYeym1SinA0",
		DeckFile:   "Dev Rel_ Learning Lab_ FIPS.pptx",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202411",
		IDInferred: true,
		VideoID:    "Pja990V0Rfc",
		DeckFile:   "Dev Rel_ Learning Lab_ Python.pptx",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202410",
		IDInferred: true,
		VideoID:    "SX4xeRzbpYo",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202409",
		IDInferred: true,
		VideoID:    "HAC0Nyt6_Uc",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202408",
		IDInferred: true,
		VideoID:    "Dbh4OMsZkNg",
		DeckFile:   "Dev Rel_ AI Learning Lab.pptx",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202406",
		IDInferred: true,
		VideoID:    "IQr-wmVzaK0",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202405",
		IDInferred: true,
		VideoID:    "cc2qxhZmMDo",
		DeckFile:   "Dev Rel_ Learning Lab_ Python.pptx",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202404",
		IDInferred: true,
		VideoID:    "0PSsJsKXqok",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202403",
		IDInferred: true,
		VideoID:    "8v8xlFnRHfs",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
	{
		ID:         "ll202402",
		IDInferred: true,
		VideoID:    "YBrczgb7e58",
		DeckFile:   "",
		GitHubID:   "",
		Era:        "old-format",
		Status:     "published",
	},
}

// PlaylistURL is the YouTube playlist containing all Learning Labs.
const PlaylistURL = "https://www.youtube.com/playlist?list=PLLjvkjPNmuZmvi2ZDXicVAWAC_mg2Jpgn"

// GitHubBaseURL is the raw content URL prefix for GitHub lab guides.
const GitHubBaseURL = "https://raw.githubusercontent.com/chainguard-dev/edu/main/content/software-security/learning-labs/"
