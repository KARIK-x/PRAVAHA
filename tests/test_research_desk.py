"""Evidence-bound research-desk tests (mission Phase D / NF-015).

The provider is always stubbed: no test makes a network call. The important
properties are that the evidence bundle is real and built before any model call,
that an unavailable provider still leaves the research tools usable, that the
sceptical review compares every number against the bundle, and that the desk has
no path to the portfolio or order code.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from megatool import llm, research_desk
from megatool.db import get_conn, init_app_db
from megatool.fundamentals import FundamentalRecord, import_records
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-16 08:00:00")


@pytest.fixture(autouse=True)
def _reset_provider():
    from megatool import catalog

    catalog.set_store_provider(None)
    yield
    catalog.set_store_provider(None)


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "rd_market.duckdb")
    rng = np.random.default_rng(31)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, size=300)))
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    s.upsert_bars(pd.DataFrame({
        "symbol": "SYN1", "trading_date": dates, "open": closes, "high": closes * 1.01,
        "low": closes * 0.99, "close": closes,
        "volume": np.full(len(closes), 1_000, dtype="int64"), "turnover": closes * 1_000,
        "percent_change": 0.0, "source": "synthetic-test", "retrieved_at": RETRIEVED,
        "validation_status": "valid", "adjustment_status": "unadjusted",
    }))
    yield s
    s.close()


@pytest.fixture
def with_fundamentals():
    init_app_db()
    with get_conn() as conn:
        import_records([
            FundamentalRecord("SYN1", "eps", 12.5, "NPR", "src-1", period_end=date(2026, 6, 30),
                              retrieved_at="2026-10-16T08:00:00+00:00"),
            FundamentalRecord("SYN1", "pe", 15.0, "ratio", "src-1", period_end=date(2026, 6, 30),
                              retrieved_at="2026-10-16T08:00:00+00:00"),
        ], conn)


class _StubProvider:
    """A provider that returns whatever text the test tells it to."""

    def __init__(self, text="", raise_error=None):
        self.text, self._raise = text, raise_error

    def complete(self, prompt, *, system=None, max_tokens=None, temperature=0.0):
        if self._raise:
            raise self._raise
        return llm.LLMResult(text=self.text, provider="stub", model="stub-1",
                             usage={"completion_tokens": 5})


def _configured(monkeypatch, provider):
    monkeypatch.setattr(llm, "provider_status", lambda p=None: {
        "provider": "stub", "model": "stub-1", "configured": True})
    monkeypatch.setattr(llm, "get_provider", lambda p=None, **kw: provider)


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #

def test_evidence_is_built_from_real_stored_rows(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    labels = {it["label"] for it in ev["items"]}
    assert "Latest stored close" in labels
    assert "Stored bars" in labels
    assert any(it["label"].startswith("Fundamental: eps") for it in ev["items"])
    # Fields that are genuinely not stored are named as missing, never defaulted.
    assert "fundamentals" not in ev["missing"]
    assert "price_bars" not in ev["missing"]
    assert "fundamentals.profit" in ev["missing"]
    # Every item names its source and calculation.
    for it in ev["items"]:
        assert it["kind"] in ("fact", "calculation")
        assert it["source"]


def test_evidence_reports_missing_inputs_without_inventing_values(store):
    ev = research_desk.build_evidence("NO_SUCH", store=store)
    assert "price_bars" in ev["missing"]
    labels = {it["label"] for it in ev["items"]}
    assert "Latest stored close" not in labels


def test_evidence_states_the_unadjusted_limitation(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    assert any("corporate-action" in lim or "unadjusted" in lim for lim in ev["limitations"])


# --------------------------------------------------------------------------- #
# Sceptical review
# --------------------------------------------------------------------------- #

def test_review_flags_numbers_that_do_not_match_the_evidence(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    review = research_desk.skeptical_review("The close is 999999.", ev)
    flag = next(c for c in review["checks"] if c["check"] == "unsupported_numeric_claims")
    assert flag["status"] == "flag"
    assert review["verdict"] in ("needs_review", "unsupported")


def test_review_passes_when_numbers_match_the_evidence(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    close = next(it["value"] for it in ev["items"] if it["label"] == "Latest stored close")
    review = research_desk.skeptical_review(f"The latest close is {close:.2f} NPR.", ev)
    flag = next(c for c in review["checks"] if c["check"] == "unsupported_numeric_claims")
    assert flag["status"] == "pass"


def test_review_flags_overclaiming_and_causal_language(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    review = research_desk.skeptical_review(
        "This is a guaranteed risk-free gain because of the news.", ev)
    by = {c["check"]: c["status"] for c in review["checks"]}
    assert by["conclusion_strength"] == "flag"
    assert by["causal_language"] == "flag"


def test_review_always_reports_structural_risks(store, with_fundamentals):
    ev = research_desk.build_evidence("SYN1", store=store)
    review = research_desk.skeptical_review("Neutral observation.", ev)
    checks = {c["check"] for c in review["checks"]}
    assert {"lookahead_bias", "overfitting", "survivorship_bias",
            "corporate_action_treatment"} <= checks


def test_review_flags_missing_inputs_as_evidence(store):
    ev = research_desk.build_evidence("NO_SUCH", store=store)
    review = research_desk.skeptical_review("Nothing to see.", ev)
    assert next(c for c in review["checks"] if c["check"] == "missing_inputs")["status"] == "flag"


# --------------------------------------------------------------------------- #
# Provider availability
# --------------------------------------------------------------------------- #

def test_missing_provider_still_returns_evidence_and_an_explicit_error(store, with_fundamentals, monkeypatch):
    monkeypatch.setattr(llm, "provider_status", lambda p=None: {
        "provider": "(disabled)", "model": "", "configured": False})
    out = research_desk.run_research("Is SYN1 expensive?", "SYN1", store=store)
    assert out["available"] is False
    assert "No AI provider is configured" in out["error"]
    assert out["evidence"]["items"], "the research tools remain usable offline"
    assert out["review"], "the review runs even without a model"


def test_successful_evidence_linked_research(store, with_fundamentals, monkeypatch):
    ev = research_desk.build_evidence("SYN1", store=store)
    close = next(it["value"] for it in ev["items"] if it["label"] == "Latest stored close")
    _configured(monkeypatch, _StubProvider(
        text=f"[Latest stored close] {close:.2f} is the last close (direct calculation)."))
    out = research_desk.run_research("What is the last close?", "SYN1", store=store)
    assert out["available"] is True
    assert out["provider"] == "stub"
    assert out["review"]["verdict"] in ("supported_by_evidence", "needs_review")


def test_provider_failure_is_reported_and_evidence_retained(store, with_fundamentals, monkeypatch):
    _configured(monkeypatch, _StubProvider(raise_error=llm.LLMUnavailable("endpoint down")))
    out = research_desk.run_research("Anything?", "SYN1", store=store)
    assert out["available"] is False
    assert "endpoint down" in out["error"]
    assert out["evidence"]["items"]


def test_malformed_or_empty_answer_is_handled(store, with_fundamentals, monkeypatch):
    _configured(monkeypatch, _StubProvider(text=""))
    out = research_desk.run_research("Anything?", "SYN1", store=store)
    assert out["available"] is True
    assert out["answer"] == ""
    assert out["review"]["verdict"] in ("supported_by_evidence", "needs_review", "unsupported")


def test_unsupported_claims_are_flagged(store, with_fundamentals, monkeypatch):
    _configured(monkeypatch, _StubProvider(
        text="The stock will definitely double, guaranteed, because of momentum. "
             "Target 123456."))
    out = research_desk.run_research("Will it double?", "SYN1", store=store)
    assert out["review"]["flags"] >= 2
    assert out["review"]["verdict"] == "unsupported"


# --------------------------------------------------------------------------- #
# Safety boundary
# --------------------------------------------------------------------------- #

def test_desk_cannot_touch_the_portfolio_or_orders():
    import inspect

    src = inspect.getsource(research_desk)
    for forbidden in ("portfolio_positions", "portfolio_transactions",
                      "place_order", "submit_order", "execute_trade"):
        assert forbidden not in src


def test_runs_are_recorded(store, with_fundamentals):
    out = research_desk.run_research("recorded?", "SYN1", store=store)
    assert "persist_error" not in out, out.get("persist_error")
    runs = research_desk.history(limit=5)
    assert runs and runs[0]["question"] == "recorded?"
