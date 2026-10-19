// Command gonepse-bridge is a thin, JSON-speaking wrapper around the *actual*
// github.com/voidarchive/go-nepse Go library. Mega Tool's Python backend runs
// it as a subprocess and parses the single JSON object it writes to stdout
// (see megatool/datasources/gonepse.py).
//
// Why a subprocess
// ----------------
// The data source is a Go library. Rather than reimplement its protocol in
// Python (which this project already did once, in nepse_official_live.py) or
// embed a Go runtime in the Python process, the library is isolated behind a
// process boundary. The Go toolchain is needed only to *build* this binary;
// the library's WASM/auth machinery never runs inside the Python process.
//
// TLS
// ---
// Certificate verification is ON and is never turned off here. Mainstream
// NEPSE clients disable it because the exchange's chain is awkward; that is a
// thing to diagnose, not to bypass. `Options.TLSVerification` stays true.
//
// Safety belt
// -----------
// When the target is the real NEPSE host, the bridge refuses to make a request
// unless MEGATOOL_NEPSE_API_AUTHORIZED=1. The Python adapter enforces the same
// gate before spawning the process, so the two checks are independent: neither
// the Python side nor a stray shell invocation can reach the live API by
// accident.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	nepse "github.com/voidarchive/go-nepse"
)

// moduleVersion is the pinned library version this bridge was built against.
// The library's own nepse.Version constant lags behind it (it reports 0.2.0
// even at module v0.2.5); both are reported so the discrepancy is visible.
const moduleVersion = "v0.2.5"

const schemaVersion = "1"

// request is the JSON object read from stdin. Only the fields an operation
// needs are required; the rest are ignored.
type request struct {
	Op         string `json:"op"`
	Symbol     string `json:"symbol,omitempty"`
	SecurityID int32  `json:"securityId,omitempty"`
	Start      string `json:"start,omitempty"`
	End        string `json:"end,omitempty"`
	Date       string `json:"date,omitempty"`
}

type errPayload struct {
	Kind    string `json:"kind"`
	Message string `json:"message"`
}

// envelope is the single JSON object written to stdout.
type envelope struct {
	OK              bool        `json:"ok"`
	SchemaVersion   string      `json:"schemaVersion"`
	Op              string      `json:"op"`
	Source          string      `json:"source"`
	ModuleVersion   string      `json:"moduleVersion"`
	LibraryVersion  string      `json:"libraryVersion"`
	TLSVerification bool        `json:"tlsVerification"`
	Data            any         `json:"data,omitempty"`
	Error           *errPayload `json:"error,omitempty"`
}

func baseEnvelope(op string) envelope {
	return envelope{
		SchemaVersion:   schemaVersion,
		Op:              op,
		Source:          "github.com/voidarchive/go-nepse",
		ModuleVersion:   moduleVersion,
		LibraryVersion:  nepse.Version,
		TLSVerification: true,
	}
}

// liveGateBlocked reports the refusal payload when a real-NEPSE call is
// attempted without the owner's authorization. It is a pure function so the
// gate can be unit-tested without touching the network.
func liveGateBlocked(baseURL string, getenv func(string) string) *errPayload {
	if baseURL != nepse.DefaultBaseURL {
		return nil
	}
	if getenv("MEGATOOL_NEPSE_API_AUTHORIZED") == "1" {
		return nil
	}
	return &errPayload{
		Kind: "unauthorized",
		Message: "live NEPSE access requires the owner authorization gate " +
			"(MEGATOOL_NEPSE_API_AUTHORIZED=1); the bridge does not bypass it",
	}
}

func main() {
	baseURL := flag.String("base-url", nepse.DefaultBaseURL,
		"NEPSE API base URL (override for tests/proxies)")
	timeout := flag.Float64("timeout", 30, "per-request HTTP timeout, seconds")
	retries := flag.Int("retries", 3, "max retries for transient failures")
	flag.Parse()

	opts := nepse.DefaultOptions()
	// The library reads the target host from Options.Config.BaseURL for every
	// request (including the token endpoint). Options.BaseURL is present in the
	// API but is not consulted, so set both to keep intent explicit.
	if opts.Config == nil {
		opts.Config = nepse.DefaultConfig()
	}
	opts.BaseURL = *baseURL
	opts.Config.BaseURL = *baseURL
	// Explicit and intentional: verification is never disabled.
	opts.TLSVerification = true
	opts.HTTPTimeout = time.Duration(*timeout * float64(time.Second))
	opts.MaxRetries = *retries

	if blocked := liveGateBlocked(opts.Config.BaseURL, os.Getenv); blocked != nil {
		env := baseEnvelope("")
		env.Error = blocked
		write(env)
		os.Exit(3)
	}

	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		env := baseEnvelope("")
		env.Error = &errPayload{Kind: "invalid_client_request",
			Message: "could not decode request JSON from stdin: " + err.Error()}
		write(env)
		os.Exit(2)
	}

	// The HTTP timeout is per request; the wall-clock budget allows for retries
	// and token acquisition. A SIGINT/SIGTERM cancels cleanly.
	ctx, cancel := context.WithTimeout(context.Background(),
		opts.HTTPTimeout*time.Duration(opts.MaxRetries+2))
	defer cancel()
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() { <-sigs; cancel() }()

	env := execute(ctx, opts, req)
	write(env)
	if !env.OK {
		os.Exit(1)
	}
}

func write(env envelope) {
	enc := json.NewEncoder(os.Stdout)
	if err := enc.Encode(env); err != nil {
		fmt.Fprintf(os.Stderr, "gonepse-bridge: encode: %v\n", err)
	}
}

// execute dispatches one operation against the real library and returns the
// populated envelope. It never panics and never hides the provider's error
// category.
func execute(ctx context.Context, opts *nepse.Options, req request) envelope {
	env := baseEnvelope(req.Op)

	client, err := nepse.NewClient(opts)
	if err != nil {
		env.Error = &errPayload{Kind: "internal_error", Message: err.Error()}
		return env
	}
	defer func() { _ = client.Close() }()

	requireSymbol := func() bool {
		if req.Symbol == "" {
			env.Error = &errPayload{Kind: "invalid_client_request",
				Message: "op " + req.Op + " requires a `symbol`"}
			return false
		}
		return true
	}

	var (
		data any
		derr error
	)
	switch req.Op {
	case "market-summary":
		data, derr = client.MarketSummary(ctx)
	case "market-status":
		data, derr = client.MarketStatus(ctx)
	case "securities":
		data, derr = client.Securities(ctx)
	case "find-security":
		if !requireSymbol() {
			return env
		}
		data, derr = client.FindSecurityBySymbol(ctx, req.Symbol)
	case "live-market":
		data, derr = client.LiveMarket(ctx)
	case "price-history":
		if !requireSymbol() {
			return env
		}
		data, derr = client.PriceHistoryBySymbol(ctx, req.Symbol, req.Start, req.End)
	case "nepse-index":
		data, derr = client.NepseIndex(ctx)
	case "sub-indices":
		data, derr = client.SubIndices(ctx)
	case "company":
		if !requireSymbol() {
			return env
		}
		data, derr = client.CompanyBySymbol(ctx, req.Symbol)
	case "company-profile":
		if !requireSymbol() {
			return env
		}
		data, derr = client.CompanyProfileBySymbol(ctx, req.Symbol)
	case "dividends":
		if !requireSymbol() {
			return env
		}
		data, derr = client.DividendsBySymbol(ctx, req.Symbol)
	case "floorsheet":
		if !requireSymbol() {
			return env
		}
		data, derr = client.FloorSheetBySymbol(ctx, req.Symbol, req.Date)
	case "market-depth":
		if !requireSymbol() {
			return env
		}
		data, derr = client.MarketDepthBySymbol(ctx, req.Symbol)
	default:
		env.Error = &errPayload{Kind: "invalid_client_request",
			Message: "unknown op " + fmt.Sprintf("%q", req.Op)}
		return env
	}

	if derr != nil {
		env.Error = classify(derr)
		return env
	}
	env.OK = true
	env.Data = data
	return env
}

// classify maps a library error onto a stable, honest error envelope. The
// library's own ErrorType is preserved verbatim; context cancellation and
// deadline are surfaced distinctly from provider errors.
func classify(err error) *errPayload {
	if errors.Is(err, context.Canceled) {
		return &errPayload{Kind: "canceled", Message: err.Error()}
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return &errPayload{Kind: "timeout", Message: err.Error()}
	}
	var ne *nepse.NepseError
	if errors.As(err, &ne) {
		return &errPayload{Kind: string(ne.Type), Message: ne.Error()}
	}
	return &errPayload{Kind: "internal_error", Message: err.Error()}
}
