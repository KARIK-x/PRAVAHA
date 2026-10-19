package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	nepse "github.com/voidarchive/go-nepse"
)

// tokenJSON is the library's own auth fixture. Using it means the bridge test
// exercises the *real* token flow (fetch -> embedded-WASM salt parse -> strip
// -> `Authorization: Salter <token>`) with no network access to NEPSE.
const tokenJSON = `{
  "salt1": 1234, "salt2": 5678, "salt3": 9012, "salt4": 3456, "salt5": 7890,
  "accessToken": "eyXJhAbBcCdDeEfFgGhHiIjJkKlLmMnNoOpPqQrRsStTuUvVwWxXyYzZ0123456789",
  "refreshToken": "rXeYfZrAeBsCdHeTfOgKhEiNjSkTlOmKnEoNp",
  "serverTime": 1735689600000
}`

type mock struct {
	srv   *httptest.Server
	mu    sync.Mutex
	auth  string
	token int
	// status overrides per-path, to test error mapping.
	status map[string]int
}

func newMock(t *testing.T) *mock {
	t.Helper()
	m := &mock{status: map[string]int{}}
	mux := http.NewServeMux()
	write := func(w http.ResponseWriter, body string) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
	mux.HandleFunc("/api/authenticate/prove", func(w http.ResponseWriter, _ *http.Request) {
		m.mu.Lock()
		m.token++
		m.mu.Unlock()
		write(w, tokenJSON)
	})
	handle := func(path, body string) {
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
			m.mu.Lock()
			m.auth = r.Header.Get("Authorization")
			st := m.status[path]
			m.mu.Unlock()
			if st != 0 {
				w.WriteHeader(st)
				return
			}
			write(w, body)
		})
	}
	handle("/api/nots/market-summary", `[
	  {"detail":"Total Turnover Rs:","value":123456.5},
	  {"detail":"Total Transactions","value":42}
	]`)
	handle("/api/nots/nepse-data/market-open",
		`{"isOpen":"OPEN","asOf":"2026-01-10","id":1}`)
	handle("/api/nots/security",
		`[{"id":131,"symbol":"NABIL","securityName":"Nabil Bank Limited","activeStatus":"A"}]`)
	handle("/api/nots/nepse-index", `[
	  {"id":58,"index":"NEPSE","close":2500.5,"high":2520,"low":2480,
	   "previousClose":2490,"change":10.5,"perChange":0.42,
	   "fiftyTwoWeekHigh":3000,"fiftyTwoWeekLow":1800,"currentValue":2500.5,
	   "generatedTime":"2026-01-10 15:00:00"},
	  {"id":57,"index":"Sensitive","close":470.1,"perChange":0.1,"currentValue":470.1}
	]`)

	m.srv = httptest.NewTLSServer(mux)
	t.Cleanup(m.srv.Close)
	return m
}

// opts returns options that point the *real* library at the local mock. The
// mock's own trusted client is injected, so this never disables verification —
// it simply trusts the test certificate. TLSVerification stays true.
func (m *mock) opts() *nepse.Options {
	o := nepse.DefaultOptions()
	o.Config.BaseURL = m.srv.URL
	o.BaseURL = m.srv.URL
	o.TLSVerification = true
	o.HTTPClient = m.srv.Client()
	o.MaxRetries = 0
	o.HTTPTimeout = 5 * time.Second
	return o
}

func (m *mock) lastAuth() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.auth
}

func TestExecuteMarketSummaryUsesRealLibraryAndAuth(t *testing.T) {
	m := newMock(t)
	env := execute(context.Background(), m.opts(), request{Op: "market-summary"})
	if !env.OK {
		t.Fatalf("expected OK, got error %+v", env.Error)
	}
	if !env.TLSVerification {
		t.Error("envelope must report tlsVerification=true")
	}
	if env.LibraryVersion == "" || env.ModuleVersion != "v0.2.5" {
		t.Errorf("version provenance missing: %q / %q", env.LibraryVersion, env.ModuleVersion)
	}
	summary, ok := env.Data.(*nepse.MarketSummary)
	if !ok {
		t.Fatalf("unexpected data type %T", env.Data)
	}
	if summary.TotalTurnover != 123456.5 || summary.TotalTransactions != 42 {
		t.Errorf("summary not decoded: %+v", summary)
	}
	if auth := m.lastAuth(); !strings.HasPrefix(auth, "Salter ") || len(auth) <= len("Salter ") {
		t.Errorf("expected the real auth header, got %q", auth)
	}
	if m.token == 0 {
		t.Error("token endpoint was never called")
	}
}

func TestExecuteMarketStatus(t *testing.T) {
	m := newMock(t)
	env := execute(context.Background(), m.opts(), request{Op: "market-status"})
	if !env.OK {
		t.Fatalf("expected OK, got %+v", env.Error)
	}
	st, ok := env.Data.(*nepse.MarketStatus)
	if !ok || !st.IsMarketOpen() || st.AsOf != "2026-01-10" {
		t.Fatalf("unexpected status %#v", env.Data)
	}
}

func TestExecuteFindSecurityBySymbol(t *testing.T) {
	m := newMock(t)
	env := execute(context.Background(), m.opts(), request{Op: "find-security", Symbol: "nabil"})
	if !env.OK {
		t.Fatalf("expected OK, got %+v", env.Error)
	}
	sec, ok := env.Data.(*nepse.Security)
	if !ok || sec.Symbol != "NABIL" || sec.ID != 131 {
		t.Fatalf("unexpected security %#v", env.Data)
	}
}

func TestExecuteNepseIndexAndSubIndices(t *testing.T) {
	m := newMock(t)
	idx := execute(context.Background(), m.opts(), request{Op: "nepse-index"})
	if !idx.OK {
		t.Fatalf("nepse-index: %+v", idx.Error)
	}
	ni, ok := idx.Data.(*nepse.NepseIndex)
	if !ok || ni.IndexValue != 2500.5 || ni.PointChange != 10.5 {
		t.Fatalf("unexpected index %#v", idx.Data)
	}

	sub := execute(context.Background(), m.opts(), request{Op: "sub-indices"})
	if !sub.OK {
		t.Fatalf("sub-indices: %+v", sub.Error)
	}
	list, ok := sub.Data.([]nepse.SubIndex)
	// The main index (id 58) is excluded, leaving the one other entry.
	if !ok || len(list) != 1 || list[0].Index != "Sensitive" {
		t.Fatalf("unexpected sub-indices %#v", sub.Data)
	}
}

func TestProviderHTTPErrorIsMappedNotHidden(t *testing.T) {
	m := newMock(t)
	m.status["/api/nots/nepse-data/market-open"] = http.StatusNotFound
	env := execute(context.Background(), m.opts(), request{Op: "market-status"})
	if env.OK {
		t.Fatal("expected failure")
	}
	if env.Error == nil || env.Error.Kind != "not_found" {
		t.Fatalf("expected not_found, got %+v", env.Error)
	}
}

func TestUnknownOpAndMissingSymbolAreClientErrors(t *testing.T) {
	m := newMock(t)
	if e := execute(context.Background(), m.opts(), request{Op: "nope"}); e.OK ||
		e.Error == nil || e.Error.Kind != "invalid_client_request" {
		t.Fatalf("unknown op: %+v", e.Error)
	}
	if e := execute(context.Background(), m.opts(), request{Op: "find-security"}); e.OK ||
		e.Error == nil || e.Error.Kind != "invalid_client_request" {
		t.Fatalf("missing symbol: %+v", e.Error)
	}
}

func TestClassifyDistinguishesTimeoutAndProviderError(t *testing.T) {
	if got := classify(context.DeadlineExceeded); got.Kind != "timeout" {
		t.Errorf("deadline => %q", got.Kind)
	}
	if got := classify(context.Canceled); got.Kind != "canceled" {
		t.Errorf("canceled => %q", got.Kind)
	}
	if got := classify(nepse.NewRateLimitError()); got.Kind != "rate_limit" {
		t.Errorf("rate limit => %q", got.Kind)
	}
}

func TestLiveGateRefusesRealHostWithoutAuthorization(t *testing.T) {
	unset := func(string) string { return "" }
	if got := liveGateBlocked(nepse.DefaultBaseURL, unset); got == nil {
		t.Fatal("real host without the gate must be blocked")
	} else if got.Kind != "unauthorized" || !strings.Contains(got.Message, "MEGATOOL_NEPSE_API_AUTHORIZED") {
		t.Fatalf("unclear refusal: %+v", got)
	}
	authorized := func(k string) string {
		if k == "MEGATOOL_NEPSE_API_AUTHORIZED" {
			return "1"
		}
		return ""
	}
	if got := liveGateBlocked(nepse.DefaultBaseURL, authorized); got != nil {
		t.Fatalf("authorized real host should pass: %+v", got)
	}
	// A non-default base URL (a test server or proxy) is not gated.
	if got := liveGateBlocked("https://example.invalid", unset); got != nil {
		t.Fatalf("non-default base URL should not be gated: %+v", got)
	}
}

func TestEnvelopeIsSingleJSONObject(t *testing.T) {
	m := newMock(t)
	env := execute(context.Background(), m.opts(), request{Op: "market-summary"})
	raw, err := json.Marshal(env)
	if err != nil {
		t.Fatal(err)
	}
	var back map[string]any
	if err := json.Unmarshal(raw, &back); err != nil {
		t.Fatalf("envelope is not decodable JSON: %v", err)
	}
	if back["ok"] != true || back["source"] != "github.com/voidarchive/go-nepse" {
		t.Fatalf("unexpected envelope %s", raw)
	}
}
