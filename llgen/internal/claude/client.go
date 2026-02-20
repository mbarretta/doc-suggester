package claude

import (
	"context"
	"fmt"
	"strings"
	"time"

	anthropic "github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
)

// Client wraps the Anthropic SDK for simple text generation.
type Client struct {
	client anthropic.Client
	model  string
}

// NewClient creates a new Claude client with the given API key and model.
func NewClient(apiKey, model string) *Client {
	c := anthropic.NewClient(option.WithAPIKey(apiKey))
	return &Client{client: c, model: model}
}

// Generate sends a system + user prompt and returns the assistant's text response.
// Retries once on error with a 5-second backoff.
func (c *Client) Generate(ctx context.Context, system, user string, maxTokens int64) (string, error) {
	return c.generateWithRetry(ctx, system, user, maxTokens, false, 0)
}

// GenerateWithThinking is like Generate but enables extended thinking.
// budgetTokens sets how many tokens Claude may use for internal reasoning (min 1024).
func (c *Client) GenerateWithThinking(ctx context.Context, system, user string, maxTokens int64, budgetTokens int64) (string, error) {
	return c.generateWithRetry(ctx, system, user, maxTokens, true, budgetTokens)
}

func (c *Client) generateWithRetry(ctx context.Context, system, user string, maxTokens int64, thinking bool, budgetTokens int64) (string, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return "", ctx.Err()
			case <-time.After(5 * time.Second):
			}
		}
		text, err := c.doGenerate(ctx, system, user, maxTokens, thinking, budgetTokens)
		if err == nil {
			return text, nil
		}
		lastErr = err
	}
	return "", lastErr
}

func (c *Client) doGenerate(ctx context.Context, system, user string, maxTokens int64, thinking bool, budgetTokens int64) (string, error) {
	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(c.model),
		MaxTokens: maxTokens,
		System: []anthropic.TextBlockParam{
			{Text: system},
		},
		Messages: []anthropic.MessageParam{
			anthropic.NewUserMessage(anthropic.NewTextBlock(user)),
		},
	}

	if thinking && budgetTokens > 0 {
		params.Thinking = anthropic.ThinkingConfigParamUnion{
			OfEnabled: &anthropic.ThinkingConfigEnabledParam{
				BudgetTokens: budgetTokens,
			},
		}
	}

	msg, err := c.client.Messages.New(ctx, params)
	if err != nil {
		return "", fmt.Errorf("claude.Generate: %w", err)
	}

	var sb strings.Builder
	for _, block := range msg.Content {
		if block.Type == "text" {
			sb.WriteString(block.Text)
		}
	}
	return sb.String(), nil
}
