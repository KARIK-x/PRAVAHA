"""BABA report builder — a registry-driven report assembly system.

The user selects *which* analyses, metrics and tables a report contains. This
module owns that contract:

* a **component registry** describing every selectable section, its category,
  its required inputs, whether the data to produce it currently exists, and the
  methodology behind it;
* a **report assembler** that runs only the selected components and nothing
  else — an unselected section can never appear in an output;
* **renderers** for XLSX, CSV, PDF and JSON that consume exactly the assembled
  sections;
* **template** persistence so a selection can be saved, loaded, renamed,
  duplicated and deleted.

Nothing here computes a figure that a more specific module already owns. The
registry's ``compute`` hooks call into :mod:`megatool.fundamentals`,
:mod:`megatool.sectors`, :mod:`megatool.journal`, :mod:`megatool.portfolio` and
:class:`megatool.market_store.MarketStore`, so a value in a report is the same
value the rest of the application would show.

A component whose data is not available is registered with ``available=False``
and a reason. It stays selectable in the UI but is reported as unavailable in
the preview and is never replaced with an invented number.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "COMPONENT_CATEGORIES",
    "ReportBuilderError",
    "ReportRequest",
    "assemble_report",
    "available_components",
    "component_by_id",
    "get_component_ids",
    "render_csv",
    "render_json",
    "render_pdf",
    "render_xlsx",
    "save_template",
    "load_template",
    "list_templates",
    "delete_template",
    "rename_template",
    "duplicate_template",
    "TEMPLATE_DIR",
]


class ReportBuilderError(ValueError):
    """An invalid component id, symbol list or render request."""


#: Bounds that keep a report request from scanning the whole universe or
#: building an unbounded document.
MAX_SYMBOLS = 200
MAX_COMPONENTS = 80


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Component:
    """One selectable report section."""

    id: str
    name: str
    category: str
    description: str
    output: str                       # table | chart | summary | detail
    requires: tuple[str, ...] = ()    # e.g. ("symbol",)
    scope: tuple[str, ...] = ("single", "multi", "sector", "portfolio", "journal")
    available: bool = True
    reason: str = ""
    methodology: str = ""
    compute: Callable[..., dict[str, Any]] | None = field(default=None, repr=False)


COMPONENT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("A_company", "Company Information"),
    ("B_market", "Market Information"),
    ("C_fundamental", "Fundamental Analysis"),
    ("D_quarterly", "Quarterly and Annual Analysis"),
    ("E_valuation", "Valuation"),
    ("F_eligibility", "Eligibility and Screening"),
    ("G_sector", "Sector Analysis"),
    ("H_comparison", "Company Comparison"),
    ("I_technical", "Technical and Price Analysis"),
    ("J_dividend", "Dividend Analysis"),
    ("K_journal", "Trading Journal"),
    ("L_portfolio", "Portfolio Analysis"),
    ("M_risk", "Risk Analysis"),
    ("N_charts", "Charts and Visualizations"),
    ("O_quality", "Data Quality and Methodology"),
    ("P_custom", "Custom Notes"),
)


def _no_data(reason: str) -> Callable[..., dict[str, Any]]:
    """A compute hook that reports unavailability instead of a number."""

    def _fn(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"available": False, "reason": reason}

    return _fn


# The registry is built lazily so importing this module never touches the data
# store. ``_build`` is called once and cached.
_REGISTRY: dict[str, Component] | None = None


def _build() -> dict[str, Component]:
    from megatool import report_components as rc

    specs = [
        # ------------------------------------------------------ A company info
        ("profile", "Company profile", "A_company", "table",
         "Identity, sector, listing date and reporting period.", ("symbol",),
         "Identity and provenance come from stored fundamentals and the sector map."),
        ("listing_age", "Listing age", "A_company", "table",
         "Years between the verified listing date and the assessment date.", ("symbol",),
         "Listing age = assessment date - listing date."),
        ("data_coverage", "Available historical coverage", "A_company", "table",
         "First and last stored bar, and the number of stored sessions.", ("symbol",),
         "Coverage is read from stored bars; it is not extrapolated."),
        ("data_refresh", "Last data refresh", "A_company", "table",
         "When the underlying records were retrieved.", ("symbol",),
         "Taken from the stored retrieval timestamp."),
        ("quality_summary", "Data-quality summary", "A_company", "summary",
         "Counts of reported, calculated, stale and missing values.", ("symbol",),
         "Derived from each field's own quality flag."),
        ("missing_summary", "Missing-data summary", "A_company", "table",
         "Every requested field that could not be produced, with a reason.", ("symbol",),
         "Only genuinely absent fields are listed."),
        # ---------------------------------------------------------- B market
        ("last_price", "Latest available price", "B_market", "table",
         "Last stored close and its date. Labelled as end-of-day, not live.", ("symbol",),
         "Last non-null stored close; never described as a live quote."),
        ("price_summary", "Historical closing-price summary", "B_market", "table",
         "First/last close, high, low and the period covered.", ("symbol",),
         "Computed over stored closes only."),
        ("market_cap", "Market capitalization", "B_market", "table",
         "Last close x shares outstanding.", ("symbol",),
         "Market cap = last stored close x shares outstanding. Price is EOD."),
        ("shares_outstanding", "Shares outstanding", "B_market", "table",
         "The share count used across all per-share metrics.", ("symbol",),
         "Documented source field; the definition is stated in the report."),
        ("paid_up_capital", "Paid-up capital", "B_market", "table",
         "Paid-up capital and its currency.", ("symbol",), "As stored."),
        ("public_float", "Public float", "B_market", "table",
         "Publicly traded shares, when the source records it.", ("symbol",),
         "Only shown when a float figure is actually stored."),
        ("holdings_split", "Public/promoter holdings", "B_market", "table",
         "Promoter vs public shareholding split.", ("symbol",),
         "Only shown when stored; never estimated."),
        ("range_52w", "52-week high and low", "B_market", "table",
         "Highest and lowest stored close over the trailing year.", ("symbol",),
         "Trailing 52 weeks of stored closes."),
        ("price_change", "Price change over selected periods", "B_market", "table",
         "Absolute and percentage change over 1M/3M/6M/1Y.", ("symbol",),
         "Close-to-close over stored sessions."),
        ("volume_turnover", "Trading volume and turnover", "B_market", "table",
         "Recent volume and turnover.", ("symbol",),
         "From stored sessions; no bar is fabricated."),
        ("liquidity", "Liquidity measures", "B_market", "table",
         "Turnover-based liquidity where enough sessions exist.", ("symbol",),
         "Requires a minimum number of sessions; otherwise unavailable."),
        ("price_volume_chart", "Price and volume chart", "B_market", "chart",
         "Close price with volume over the stored range.", ("symbol",),
         "Only from stored bars."),
        ("price_table", "Historical price-performance table", "B_market", "table",
         "Monthly closes over the stored range.", ("symbol",),
         "Resampled from stored bars; gaps are shown, not filled."),
        # ------------------------------------------------------ C fundamental
        ("eps_quarterly", "Quarterly EPS", "C_fundamental", "table",
         "Per-quarter EPS, each labelled with its own period.", ("symbol",),
         "Quarterly EPS is never substituted with annual EPS."),
        ("eps_annual", "Annual EPS", "C_fundamental", "table",
         "Annual EPS for each stored financial year.", ("symbol",), "As stored."),
        ("eps_ttm", "TTM EPS", "C_fundamental", "table",
         "Trailing-twelve-month EPS, only when the source basis verifies.", ("symbol",),
         "TTM EPS requires four consecutive quarters; otherwise unavailable."),
        ("eps_annualized", "Annualized quarterly EPS (estimate)", "C_fundamental", "table",
         "Quarterly EPS x 4, explicitly labelled as an estimate.", ("symbol",),
         "Estimate only; the assumption is stated wherever it appears."),
        ("net_worth_ps", "Net worth per share", "C_fundamental", "table",
         "Net worth / shares outstanding.", ("symbol",),
         "Net worth per share = net worth / shares outstanding."),
        ("book_value_ps", "Book value per share", "C_fundamental", "table",
         "Book value per share where equivalent and justified.", ("symbol",),
         "Only shown when the source field is genuinely equivalent."),
        ("revenue", "Revenue", "C_fundamental", "table", "Reported revenue by period.",
         ("symbol",), "As stored."),
        ("net_profit", "Net profit", "C_fundamental", "table", "Reported net profit.",
         ("symbol",), "As stored."),
        ("profit_margin", "Profit margin", "C_fundamental", "table",
         "Net profit / revenue when both exist and are compatible.", ("symbol",),
         "Only computed when revenue and profit share a period."),
        ("earnings_growth", "Earnings growth", "C_fundamental", "table",
         "Year-over-year and sequential EPS growth.", ("symbol",),
         "Growth requires two comparable periods of the same basis."),
        ("revenue_growth", "Revenue growth", "C_fundamental", "table",
         "Year-over-year revenue growth.", ("symbol",),
         "Only across periods reported on the same basis."),
        ("roe", "Return on equity", "C_fundamental", "table",
         "Net profit / equity when both are available.", ("symbol",),
         "Requires a compatible equity figure."),
        ("roa", "Return on assets", "C_fundamental", "table",
         "Net profit / total assets when both are available.", ("symbol",),
         "Requires a compatible total-assets figure."),
        ("pe_ratio", "P/E ratio", "C_fundamental", "table",
         "Last close / EPS, using a stated EPS period.", ("symbol",),
         "P/E is suppressed when EPS is zero, negative, missing or stale."),
        ("pb_ratio", "Price-to-book ratio", "C_fundamental", "table",
         "Last close / book value per share.", ("symbol",),
         "Only when a valid book value per share exists."),
        ("dps", "Dividend per share", "C_fundamental", "table", "DPS by period.",
         ("symbol",), "As stored."),
        ("dividend_yield", "Dividend yield", "C_fundamental", "table",
         "DPS / last close, with the denominator stated.", ("symbol",),
         "Denominator and date are always shown next to the yield."),
        ("fundamental_trend", "Fundamental trend table", "C_fundamental", "table",
         "EPS, revenue and profit across stored periods.", ("symbol",),
         "Only stored periods are shown."),
        ("fundamental_summary", "Fundamental summary", "C_fundamental", "summary",
         "A short narrative built from the figures above.", ("symbol",),
         "Generated from computed values only; no external claims."),
        ("fundamental_quality", "Fundamental data-quality assessment", "C_fundamental",
         "summary", "Which fundamental fields are stale, missing or conflicting.",
         ("symbol",), "Each flag comes from the field's own quality status."),
        # ---------------------------------------------------------- D quarterly
        ("q1_results", "Q1 results", "D_quarterly", "table", "First-quarter figures.",
         ("symbol",), "Only when a Q1 record exists."),
        ("q2_results", "Q2 results", "D_quarterly", "table", "Second-quarter figures.",
         ("symbol",), "Only when a Q2 record exists."),
        ("q3_results", "Q3 results", "D_quarterly", "table", "Third-quarter figures.",
         ("symbol",), "Only when a Q3 record exists."),
        ("q4_results", "Q4 results", "D_quarterly", "table", "Fourth-quarter figures.",
         ("symbol",), "Only when a Q4 record exists."),
        ("q_eps_comparison", "Quarterly EPS comparison", "D_quarterly", "table",
         "EPS side by side across quarters.", ("symbol",),
         "Quarters are never filled by copying another quarter."),
        ("q_revenue_comparison", "Quarterly revenue comparison", "D_quarterly", "table",
         "Revenue side by side across quarters.", ("symbol",), "As stored."),
        ("q_profit_comparison", "Quarterly profit comparison", "D_quarterly", "table",
         "Net profit side by side across quarters.", ("symbol",), "As stored."),
        ("yoy_growth", "Year-over-year growth", "D_quarterly", "table",
         "Same-quarter growth across years.", ("symbol",),
         "Only when both years report that quarter."),
        ("seq_growth", "Sequential-quarter growth", "D_quarterly", "table",
         "Growth from the previous quarter.", ("symbol",),
         "Requires the immediately preceding quarter."),
        ("annual_summary", "Annual financial summary", "D_quarterly", "table",
         "Annual EPS, revenue and profit.", ("symbol",), "As stored."),
        ("q_trend_chart", "Quarterly trend chart", "D_quarterly", "chart",
         "EPS and profit by quarter.", ("symbol",), "Only stored quarters."),
        ("annual_trend_chart", "Annual trend chart", "D_quarterly", "chart",
         "Annual EPS and profit by year.", ("symbol",), "Only stored years."),
        ("missing_quarters", "Missing-quarter report", "D_quarterly", "table",
         "Quarters with no stored record.", ("symbol",),
         "Absence is reported, never inferred."),
        ("comparability", "Restatement and comparability warnings", "D_quarterly",
         "table", "Periods that may not be comparable.", ("symbol",),
         "Only reported when the source records a restatement."),
        # ---------------------------------------------------------- E valuation
        ("pe_analysis", "P/E analysis", "E_valuation", "table",
         "P/E against its own history and peers.", ("symbol",),
         "Only when a valid EPS basis exists."),
        ("pb_analysis", "Price-to-book analysis", "E_valuation", "table",
         "P/B against its own history and peers.", ("symbol",),
         "Only when a valid book value exists."),
        ("networth_analysis", "Net-worth analysis", "E_valuation", "table",
         "Net worth per share against price.", ("symbol",),
         "Net worth per share and price must share a date basis."),
        ("divyield_analysis", "Dividend-yield analysis", "E_valuation", "table",
         "Yield over time and against peers.", ("symbol",),
         "Denominator stated for every yield."),
        ("peer_valuation", "Peer valuation comparison", "E_valuation", "table",
         "P/E, P/B and yield against selected peers.", ("symbol",),
         "Only peers with valid, comparable inputs are ranked."),
        ("sector_valuation", "Sector valuation comparison", "E_valuation", "table",
         "The same metrics aggregated across a sector.", ("sector",),
         "Only companies with valid, comparable inputs are included."),
        ("valuation_formulas", "Valuation input and formula table", "E_valuation", "table",
         "Every input, its unit, its source and the formula used.", ("symbol",),
         "This is what makes each ratio auditable."),
        ("valuation_limits", "Valuation limitations and warnings", "E_valuation",
         "table", "Why a ratio may not be meaningful here.", ("symbol",),
         "No unsupported intrinsic-value estimate is generated."),
        # ------------------------------------------------------ F eligibility
        ("elig_listing_age", "Listing-age eligibility", "F_eligibility", "table",
         "Two-year rule against a verified listing date.", ("symbol",),
         "Uses the verified listing date and a defined assessment date."),
        ("elig_share_count", "Minimum-share-count eligibility", "F_eligibility", "table",
         "The 10,000-share rule against an explicitly defined field.", ("symbol",),
         "The share-count field is stated in the configuration and report."),
        ("elig_networth", "Net-worth versus paid-up eligibility", "F_eligibility", "table",
         "Net worth must not fall below paid-up value.", ("symbol",),
         "Only compared when both figures share units."),
        ("elig_profit", "Profit-history eligibility", "F_eligibility", "table",
         "Recorded net profit in the selected period.", ("symbol",),
         "Only counts a profit actually recorded for that period."),
        ("elig_dividend", "Dividend-history eligibility", "F_eligibility", "table",
         "Qualifying dividend-earning history.", ("symbol",),
         "Qualification follows the configured rule."),
        ("elig_result", "Complete eligibility result", "F_eligibility", "table",
         "Eligible, not eligible, or needs review, with the reason.", ("symbol",),
         "Missing or contradictory data can never silently pass a rule."),
        ("elig_failed", "Failed-criteria explanation", "F_eligibility", "table",
         "Each failed rule with its supporting values.", ("symbol",),
         "Values, units, source and period are shown per rule."),
        ("elig_lists", "Eligible / ineligible / needs-review lists", "F_eligibility",
         "table", "The three result groups.", ("symbol",), "Derived from elig_result."),
        ("elig_config", "Screening configuration", "F_eligibility", "table",
         "The configured thresholds and assessment period.", ("symbol",),
         "Rule definitions travel with the report."),
        # ---------------------------------------------------------- G sector
        ("sector_overview", "Sector overview", "G_sector", "table",
         "Companies, data coverage and freshness per sector.", ("sector",),
         "Actual counts are reported separately from provisional targets."),
        ("sector_table", "Sector company table", "G_sector", "table",
         "Every company in a sector with its key figures.", ("sector",),
         "Companies with missing data stay listed and are flagged."),
        ("sector_eps_rank", "EPS ranking", "G_sector", "table",
         "Ranked EPS across a sector.", ("sector",),
         "Only companies with a valid, comparable EPS are ranked."),
        ("sector_pe_rank", "P/E ranking", "G_sector", "table", "Ranked P/E.",
         ("sector",), "Companies without a valid P/E are listed as unranked."),
        ("sector_networth_rank", "Net-worth ranking", "G_sector", "table",
         "Ranked net worth per share.", ("sector",), "Comparable basis only."),
        ("sector_cap_rank", "Market-cap ranking", "G_sector", "table",
         "Ranked market capitalisation.", ("sector",), "Requires a price and a share count."),
        ("sector_dividend_rank", "Dividend ranking", "G_sector", "table",
         "Ranked dividend metrics.", ("sector",), "Only companies with records."),
        ("sector_growth_rank", "Profit-growth ranking", "G_sector", "table",
         "Ranked profit growth.", ("sector",), "Requires two comparable periods."),
        ("sector_q_rank", "Quarterly-performance ranking", "G_sector", "table",
         "Ranked quarterly performance.", ("sector",), "Only companies with that quarter."),
        ("sector_comparison", "Company comparison table", "G_sector", "table",
         "Side-by-side metrics across a sector.", ("sector",),
         "Incompatible reporting periods are flagged, not hidden."),
        ("sector_distribution", "Sector distribution chart", "G_sector", "chart",
         "Distribution of a chosen metric across a sector.", ("sector",),
         "Only companies with valid values are plotted."),
        ("sector_outliers", "Outlier and missing-data report", "G_sector", "table",
         "Outliers and gaps within a sector.", ("sector",),
         "Outliers are flagged, not removed."),
        # ------------------------------------------------------ H comparison
        ("cmp_overview", "Selected-company overview", "H_comparison", "table",
         "Identity and one-line figures per company.", ("multi",),
         "One row per selected company."),
        ("cmp_eps", "EPS comparison", "H_comparison", "table", "EPS side by side.",
         ("multi",), "Each period labelled with its own basis."),
        ("cmp_networth", "Net-worth comparison", "H_comparison", "table",
         "Net worth per side.", ("multi",), "Comparable basis only."),
        ("cmp_pe", "P/E comparison", "H_comparison", "table", "P/E side by side.",
         ("multi",), "Invalid P/E shown as unavailable, never as zero."),
        ("cmp_pb", "Price-to-book comparison", "H_comparison", "table", "P/B side by side.",
         ("multi",), "Only where a valid book value exists."),
        ("cmp_dividend", "Dividend comparison", "H_comparison", "table",
         "DPS and yield side by side.", ("multi",), "Denominators stated."),
        ("cmp_growth", "Quarterly growth comparison", "H_comparison", "table",
         "Growth rates side by side.", ("multi",), "Only comparable periods."),
        ("cmp_profitability", "Profitability comparison", "H_comparison", "table",
         "Margins and returns side by side.", ("multi",), "Only where inputs exist."),
        ("cmp_price_perf", "Price-performance comparison", "H_comparison", "table",
         "Return over the selected horizon.", ("multi",), "Close-to-close."),
        ("cmp_liquidity", "Volume/liquidity comparison", "H_comparison", "table",
         "Liquidity side by side.", ("multi",), "Requires enough sessions."),
        ("cmp_eligibility", "Eligibility comparison", "H_comparison", "table",
         "Eligibility result per company.", ("multi",), "Same configured rules for all."),
        ("cmp_side_by_side", "Side-by-side financial table", "H_comparison", "table",
         "The combined comparison grid.", ("multi",), "Missing cells stay empty."),
        ("cmp_charts", "Comparison charts", "H_comparison", "chart",
         "Overlay of the selected metric.", ("multi",), "Only stored data."),
        ("cmp_warnings", "Missing-data and comparability warnings", "H_comparison",
         "table", "What cannot be compared and why.", ("multi",),
         "Incompatible periods are flagged."),
        # ---------------------------------------------------------- I technical
        ("trend", "Price trend", "I_technical", "chart", "Close-price trend.",
         ("symbol",), "From stored bars."),
        ("perf_multi", "Multi-period price performance", "I_technical", "table",
         "Return over several horizons.", ("symbol",), "Close-to-close."),
        ("ma", "Moving averages", "I_technical", "table", "MA20/MA50/MA200.",
         ("symbol",), "Simple moving averages over stored closes."),
        ("rsi", "RSI", "I_technical", "table", "Relative Strength Index.",
         ("symbol",), "Wilder's RSI over stored closes."),
        ("macd", "MACD", "I_technical", "table", "MACD line, signal and histogram.",
         ("symbol",), "Standard 12/26/9 over stored closes."),
        ("volatility", "Volatility", "I_technical", "table",
         "Annualised return volatility.", ("symbol",),
         "Standard deviation of log returns, annualised; window stated."),
        ("volume_analysis", "Volume analysis", "I_technical", "table",
         "Volume trend and average.", ("symbol",), "From stored sessions."),
        ("support_resistance", "Support and resistance", "I_technical", "table",
         "Recent swing levels.", ("symbol",), "Derived from stored highs and lows."),
        ("fibonacci", "Fibonacci retracements and extensions", "I_technical", "table",
         "Retracement and extension levels.", ("symbol",),
         "Uses megatool.ta.fibonacci over stored extremes."),
        ("candlestick", "Candlestick analysis", "I_technical", "table",
         "Candle-based observations over stored bars.", ("symbol",),
         "Only where OHLC bars are stored."),
        ("patterns", "Chart-pattern analysis", "I_technical", "table",
         "Detected patterns over stored bars.", ("symbol",),
         "Only patterns the implementation actually detects."),
        ("elliott", "Elliott Wave analysis", "I_technical", "table",
         "Wave count and rule evaluation.", ("symbol",),
         "Certainty is a count of decidable rules passed, not a probability."),
        ("mtf_trend", "Multi-timeframe trend analysis", "I_technical", "table",
         "Trend across daily/weekly/monthly.", ("symbol",),
         "Requires aligned history on each timeframe."),
        ("ta_summary", "Technical indicator summary", "I_technical", "summary",
         "What the indicators collectively say.", ("symbol",),
         "Narrative from computed values only."),
        ("tv_chart", "Price/volume charts", "I_technical", "chart",
         "Price with volume and indicators.", ("symbol",), "Only stored bars."),
        ("technical_warnings", "Technical data-quality warnings", "I_technical", "table",
         "Gaps and coverage limits behind the indicators.", ("symbol",),
         "Actual data period and gaps are shown."),
        # ---------------------------------------------------------- J dividend
        ("div_history", "Dividend history", "J_dividend", "table",
         "Every recorded distribution.", ("symbol",), "As stored."),
        ("div_cash", "Cash dividends", "J_dividend", "table", "Cash DPS by period.",
         ("symbol",), "Cash dividends only."),
        ("div_bonus", "Bonus-share history", "J_dividend", "table",
         "Bonus shares where supported.", ("symbol",),
         "Only when the source records bonus shares."),
        ("div_yield", "Dividend yield", "J_dividend", "table", "Yield with denominator.",
         ("symbol",), "Denominator and date always shown."),
        ("div_consistency", "Dividend consistency", "J_dividend", "table",
         "Consecutive periods of distributions.", ("symbol",),
         "Absence is reported, not assumed."),
        ("div_comparison", "Dividend comparison across companies", "J_dividend", "table",
         "DPS and yield across companies.", ("multi",), "Denominators stated."),
        ("div_missing", "Missing dividend records", "J_dividend", "table",
         "Periods with no recorded distribution.", ("symbol",),
         "Reported as missing."),
        ("div_method", "Dividend calculation methodology", "J_dividend", "table",
         "Formulas and denominators used.", ("symbol",), "Auditable by construction."),
        # ---------------------------------------------------------- K journal
        ("j_ledger", "Complete transaction ledger", "K_journal", "table",
         "Every journal entry.", ("journal",),
         "Private: only ever produced for an authorised local session."),
        ("j_day", "Selected-day transactions", "K_journal", "table",
         "Entries for the chosen date.", ("journal",), "Date-bounded."),
        ("j_buys", "Buy transactions", "K_journal", "table", "Buy-side entries.",
         ("journal",), "Private."),
        ("j_sells", "Sell transactions", "K_journal", "table", "Sell-side entries.",
         ("journal",), "Private."),
        ("j_day_summary", "Daily transaction summary", "K_journal", "table",
         "Per-date totals.", ("journal",), "Private."),
        ("j_month_summary", "Monthly transaction summary", "K_journal", "table",
         "Per-month totals.", ("journal",), "Private."),
        ("j_symbol_summary", "Symbol-wise transaction summary", "K_journal", "table",
         "Per-symbol totals.", ("journal",), "Private."),
        ("j_broker_summary", "Broker-wise summary", "K_journal", "table",
         "Per-broker totals.", ("journal",), "Private."),
        ("j_charges", "Transaction charges", "K_journal", "table",
         "Commission, fees and taxes per entry.", ("journal",), "As recorded."),
        ("j_gross_purchase", "Gross purchase amounts", "K_journal", "table",
         "Total bought, gross.", ("journal",), "Quantity x price."),
        ("j_gross_sale", "Gross sale amounts", "K_journal", "table",
         "Total sold, gross.", ("journal",), "Quantity x price."),
        ("j_net_purchase", "Net purchase costs", "K_journal", "table",
         "Gross plus charges.", ("journal",), "Gross + applicable charges."),
        ("j_net_sale", "Net sale proceeds", "K_journal", "table",
         "Gross minus charges.", ("journal",), "Gross - applicable charges."),
        ("j_realized", "Realized profit/loss", "K_journal", "table",
         "Realized P&L with the cost basis stated.", ("journal",),
         "The cost-basis method is stated and never switched silently."),
        ("j_holdings", "Holdings", "K_journal", "table", "Current positions.",
         ("journal",), "Derived from the ledger."),
        ("j_available", "Available quantities", "K_journal", "table",
         "Sellable quantity per symbol.", ("journal",),
         "Negative or inconsistent balances are flagged."),
        ("j_avg_cost", "Average acquisition cost", "K_journal", "table",
         "Weighted average cost per symbol.", ("journal",),
         "Weighted by quantity over recorded buys."),
        ("j_unrealized", "Unrealized profit/loss", "K_journal", "table",
         "Open-position P&L against a valid stored price.", ("journal",),
         "Only where a valid market price exists."),
        ("j_open_positions", "Open positions", "K_journal", "table", "Symbols held.",
         ("journal",), "Derived from the ledger."),
        ("j_closed_positions", "Closed positions", "K_journal", "table",
         "Symbols fully sold.", ("journal",), "Derived from the ledger."),
        ("j_warnings", "Transaction validation warnings", "K_journal", "table",
         "Duplicates, overselling, missing fields.", ("journal",),
         "Problems are surfaced, never concealed."),
        ("j_reconciliation", "Reconciliation discrepancies", "K_journal", "table",
         "Unresolved differences against broker data.", ("journal",),
         "Only computed where broker data was supplied."),
        ("j_notes", "Journal notes", "K_journal", "table", "Free-text notes.",
         ("journal",), "As recorded."),
        ("j_audit", "Journal audit history", "K_journal", "table",
         "Creation and update timestamps per entry.", ("journal",),
         "The audit trail is preserved on edit."),
        # ---------------------------------------------------------- L portfolio
        ("p_holdings", "Portfolio holdings", "L_portfolio", "table",
         "Positions with quantity and value.", ("portfolio",),
         "Derived from the ledger plus manual positions."),
        ("p_allocation", "Portfolio allocation", "L_portfolio", "table",
         "Weight per position.", ("portfolio",), "Weight = value / total value."),
        ("p_sector_exposure", "Sector exposure", "L_portfolio", "table",
         "Value by sector.", ("portfolio",),
         "Only holdings with a known sector are attributed."),
        ("p_concentration", "Symbol concentration", "L_portfolio", "table",
         "Largest positions and their weights.", ("portfolio",), "Concentration risk."),
        ("p_position_weights", "Position weights", "L_portfolio", "table",
         "Percentage weight per position.", ("portfolio",), "Of total market value."),
        ("p_cost_basis", "Cost basis", "L_portfolio", "table",
         "Acquisition cost per position.", ("portfolio",), "Stated method."),
        ("p_market_value", "Market value", "L_portfolio", "table",
         "Current value per position.", ("portfolio",),
         "Requires a valid stored price."),
        ("p_realized", "Realized P&L", "L_portfolio", "table", "Closed-position P&L.",
         ("portfolio",), "Stated cost-basis method."),
        ("p_unrealized", "Unrealized P&L", "L_portfolio", "table", "Open-position P&L.",
         ("portfolio",), "Requires a valid stored price."),
        ("p_total", "Total P&L", "L_portfolio", "table", "Realized plus unrealized.",
         ("portfolio",), "Sum of the two."),
        ("p_cash", "Cash and available balance", "L_portfolio", "table",
         "Only when the ledger actually tracks cash.", ("portfolio",),
         "Never invented."),
        ("p_performance", "Portfolio performance", "L_portfolio", "table",
         "Return over the selected horizon.", ("portfolio",),
         "Over stored sessions."),
        ("p_exposure_concentration", "Exposure concentration", "L_portfolio", "table",
         "Sector and symbol concentration combined.", ("portfolio",), "Both dimensions."),
        ("p_warnings", "Portfolio data-quality warnings", "L_portfolio", "table",
         "Missing prices and stale inputs.", ("portfolio",), "Surfaced, not hidden."),
        # ---------------------------------------------------------- M risk
        ("r_volatility", "Historical volatility", "M_risk", "table",
         "Annualised volatility over a stated window.", ("symbol",),
         "Window and observation count always stated."),
        ("r_drawdown", "Maximum drawdown", "M_risk", "table",
         "Largest peak-to-trough decline.", ("symbol",),
         "Over stored closes."),
        ("r_distribution", "Return distribution", "M_risk", "table",
         "Percentiles of the return series.", ("symbol",),
         "Sample size stated."),
        ("r_downside", "Downside volatility", "M_risk", "table",
         "Volatility of negative returns only.", ("symbol",),
         "Requires enough negative-return observations."),
        ("r_gaps", "Price-gap analysis", "M_risk", "table",
         "Overnight/session gaps over a threshold.", ("symbol",),
         "Threshold stated."),
        ("r_liquidity_risk", "Volume/liquidity risk", "M_risk", "table",
         "Turnover volatility and gaps.", ("symbol",),
         "Requires enough sessions."),
        ("r_concentration", "Portfolio concentration", "M_risk", "table",
         "Symbol and sector concentration.", ("portfolio",), "Both dimensions."),
        ("r_correlation", "Correlation between selected symbols", "M_risk", "table",
         "Return correlation matrix.", ("multi",),
         "Only over synchronized observations; the count is stated."),
        ("r_beta", "Beta", "M_risk", "table",
         "Beta against a defined benchmark.", ("symbol",),
         "Requires a named benchmark and enough synchronized observations."),
        ("r_coverage", "Data coverage and limitations", "M_risk", "table",
         "Observation counts and gaps behind each measure.", ("symbol",),
         "Every measure states its own coverage."),
        # ---------------------------------------------------------- N charts
        ("c_price", "Price chart", "N_charts", "chart", "Close-price line.",
         ("symbol",), "Stored bars only."),
        ("c_volume", "Volume chart", "N_charts", "chart", "Volume bars.",
         ("symbol",), "Stored sessions only."),
        ("c_eps_trend", "EPS trend", "N_charts", "chart", "EPS by period.",
         ("symbol",), "Stored periods only."),
        ("c_profit_trend", "Profit trend", "N_charts", "chart", "Profit by period.",
         ("symbol",), "Stored periods only."),
        ("c_revenue_trend", "Revenue trend", "N_charts", "chart", "Revenue by period.",
         ("symbol",), "Stored periods only."),
        ("c_dividend", "Dividend chart", "N_charts", "chart", "DPS by period.",
         ("symbol",), "Stored periods only."),
        ("c_comparison", "Company comparison chart", "N_charts", "chart",
         "Metric overlay across companies.", ("multi",), "Stored data only."),
        ("c_sector_dist", "Sector distribution", "N_charts", "chart",
         "Chosen metric across a sector.", ("sector",), "Valid values only."),
        ("c_valuation", "Valuation comparison", "N_charts", "chart",
         "P/E, P/B or yield across companies.", ("multi",), "Valid values only."),
        ("c_allocation", "Portfolio allocation", "N_charts", "chart",
         "Allocation by position and sector.", ("portfolio",), "Derived values."),
        ("c_pnl", "Realized/unrealized P&L", "N_charts", "chart",
         "P&L breakdown.", ("portfolio",), "Derived values."),
        ("c_risk", "Risk chart", "N_charts", "chart",
         "Drawdown and return distribution.", ("symbol",), "Stored data only."),
        ("c_technical", "Technical indicators", "N_charts", "chart",
         "Price with indicators overlaid.", ("symbol",), "Stored data only."),
        # ---------------------------------------------------------- O quality
        ("q_sources", "Data source list", "O_quality", "table",
         "Every source a figure came from.", (),
         "Provenance is mandatory, not optional."),
        ("q_freshness", "Source freshness", "O_quality", "table",
         "Retrieval timestamps per source.", (), "As recorded."),
        ("q_period_coverage", "Reporting-period coverage", "O_quality", "table",
         "Which periods have stored data.", (), "Absence reported."),
        ("q_missing", "Missing fields", "O_quality", "table",
         "Fields that could not be produced.", (), "With reasons."),
        ("q_stale", "Stale data", "O_quality", "table", "Fields past their freshness.",
         (), "Age stated."),
        ("q_conflicts", "Conflicting values", "O_quality", "table",
         "Where sources disagree.", (), "Both values shown."),
        ("q_formulas", "Formula and methodology notes", "O_quality", "table",
         "Every calculation, its inputs and its formula.", (),
         "This is what makes a figure auditable."),
        ("q_estimates", "Estimated values", "O_quality", "table",
         "Every value that is an estimate, and its assumptions.", (),
         "Estimates are always labelled where they appear."),
        ("q_unavailable", "Unavailable analyses", "O_quality", "table",
         "Selected components that could not run, and why.", (),
         "Never replaced with invented data."),
        ("q_reconciliation", "Reconciliation warnings", "O_quality", "table",
         "Unresolved differences.", (), "Surfaced."),
        # ---------------------------------------------------------- P custom
        ("custom_title", "Custom report title", "P_custom", "summary",
         "A title supplied by the user.", (), "User-supplied."),
        ("custom_subtitle", "Subtitle", "P_custom", "summary",
         "A subtitle supplied by the user.", (), "User-supplied."),
        ("custom_notes", "Personal analysis notes", "P_custom", "summary",
         "Free-text observations.", (),
         "User notes are labelled as such and never presented as verified facts."),
        ("custom_observations", "Selected observations", "P_custom", "summary",
         "Specific figures the user wants highlighted.", (), "User-selected."),
        ("custom_date", "Report date", "P_custom", "summary",
         "Generation timestamp.", (), "Generation time."),
        ("custom_symbols", "Selected symbols", "P_custom", "summary",
         "The symbols the report covers.", (), "User-selected."),
        ("custom_period", "Selected reporting period", "P_custom", "summary",
         "The period the report covers.", (), "User-selected."),
        ("custom_cover", "Cover page", "P_custom", "summary",
         "A title page for the report.", (), "Formatting only."),
        ("custom_exec_summary", "Executive summary", "P_custom", "summary",
         "A short overview built from the report's own figures.", (),
         "Built from computed values only; no external claims."),
    ]

    registry: dict[str, Component] = {}
    for (cid, name, cat, output, desc, requires, methodology) in specs:
        compute = getattr(rc, f"compute_{cid}", None)
        available = compute is not None
        registry[cid] = Component(
            id=cid, name=name, category=cat, description=desc, output=output,
            requires=requires, available=available,
            reason="" if available else "no data source currently produces this",
            methodology=methodology, compute=compute,
        )
    return registry


def _registry() -> dict[str, Component]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build()
    return _REGISTRY


def get_component_ids() -> list[str]:
    return list(_registry())


def component_by_id(cid: str) -> Component:
    reg = _registry()
    if cid not in reg:
        raise ReportBuilderError(f"unknown report component {cid!r}")
    return reg[cid]


def available_components() -> dict[str, list[str]]:
    """Component ids grouped by category, available ones marked."""
    reg = _registry()
    out: dict[str, list[str]] = {}
    for cid, c in reg.items():
        out.setdefault(c.category, []).append(cid)
    return out


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
@dataclass
class ReportRequest:
    """What the user asked for."""

    components: list[str]
    symbols: list[str] = field(default_factory=list)
    sector: str | None = None
    period: str | None = None
    fmt: str = "xlsx"
    title: str | None = None
    notes: str | None = None
    as_of: date | None = None

    def __post_init__(self) -> None:
        # Bounds are checked on the raw input: deduplicating first would let a
        # request of a million identical ids past a count limit.
        if len(self.components) > MAX_COMPONENTS:
            raise ReportBuilderError(
                f"too many components (max {MAX_COMPONENTS})")
        if len(self.symbols) > MAX_SYMBOLS:
            raise ReportBuilderError(f"too many symbols (max {MAX_SYMBOLS})")
        self.components = list(dict.fromkeys(self.components))
        self.symbols = list(dict.fromkeys(s.strip().upper() for s in self.symbols if s.strip()))
        self.fmt = (self.fmt or "xlsx").lower()
        if self.fmt not in ("xlsx", "csv", "pdf", "json"):
            raise ReportBuilderError(f"unsupported format {self.fmt!r}")


def _hook_source(comp: Component) -> str:
    """The compute hook's source, or "" when it cannot be introspected."""
    import inspect

    if comp.compute is None:
        return ""
    try:
        return inspect.getsource(comp.compute)
    except (OSError, TypeError):  # pragma: no cover - exotic callables
        return ""


def _run_component(comp: Component, req: ReportRequest) -> dict[str, Any]:
    """Run one component, expanding a single-symbol hook across every symbol.

    A component whose hook reads ``req.symbols[0]`` describes one company. When
    several symbols are requested, calling it once would silently report only the
    first - the worst kind of wrong answer, because it looks complete. Such hooks
    are therefore run once per symbol and their rows concatenated. Hooks that
    already iterate ``req.symbols`` and chart hooks (whose output is one series)
    are called once.
    """
    src = _hook_source(comp)
    single = "symbols[0]" in src
    if not single or len(req.symbols) < 2 or comp.output == "chart":
        return comp.compute(req)  # type: ignore[misc]

    from dataclasses import replace

    merged: dict[str, Any] | None = None
    pairs: list[tuple[str, list[Any]]] = []
    reasons: list[str] = []
    for sym in req.symbols:
        try:
            part = comp.compute(replace(req, symbols=[sym]))  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001 - one symbol must not lose the rest
            reasons.append(f"{sym}: {exc}")
            continue
        if not part.get("available", True):
            reasons.append(f"{sym}: {part.get('reason') or 'unavailable'}")
            continue
        if merged is None:
            merged = {k: v for k, v in part.items() if k != "rows"}
        pairs.extend((sym, list(row)) for row in (part.get("rows") or []))

    if merged is None:
        return {"name": comp.name, "available": False,
                "reason": "; ".join(reasons) or "no requested symbol produced data"}

    # Merged rows must say which company each one belongs to. A section whose
    # first cell already is the symbol is left alone; one that starts with a
    # label ("Reported P/E") gets a Symbol column so two companies can never be
    # read as one confusing list.
    rows: list[list[Any]] = []
    needed_header = False
    for sym, row in pairs:
        if row and str(row[0]) == str(sym):
            rows.append(row)
        else:
            rows.append([sym, *row])
            needed_header = True
    if needed_header:
        headers = merged.get("headers")
        if headers:
            merged["headers"] = ["Symbol", *headers]
    merged["rows"] = rows
    merged["available"] = True
    return merged


def assemble_report(req: ReportRequest) -> dict[str, Any]:
    """Run the selected components and return exactly those sections.

    The returned dict has one entry per *selected and available* component, plus
    a ``quality.unavailable`` list naming the selected components that could not
    run and why. An unselected component is never computed and never appears.
    """
    from megatool import report_components as rc

    # A full report asks the same tables dozens of times. The memo is scoped to
    # this call (ContextVar), so it cannot leak a stale value into a later
    # request.
    with rc.report_cache():
        return _assemble_report(req)


def _assemble_report(req: ReportRequest) -> dict[str, Any]:
    reg = _registry()
    unknown = [c for c in req.components if c not in reg]
    if unknown:
        raise ReportBuilderError("unknown component(s): " + ", ".join(sorted(unknown)))

    sections: dict[str, Any] = {}
    unavailable: list[dict[str, str]] = []
    for cid in req.components:
        comp = reg[cid]
        if comp.available and comp.compute is not None:
            try:
                result = _run_component(comp, req)
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                unavailable.append({"id": cid, "name": comp.name, "reason": str(exc)})
                continue
            sections[cid] = result
            if not result.get("available", True):
                # The hook ran but the data is not there. The section is kept so
                # the preview can name it, and it is *also* listed as unavailable
                # so every renderer discloses the gap instead of dropping it.
                unavailable.append({
                    "id": cid, "name": comp.name,
                    "reason": result.get("reason") or comp.reason
                    or "the data source returned nothing",
                })
        else:
            unavailable.append({"id": cid, "name": comp.name, "reason": comp.reason})

    return {
        "title": req.title or "PRAVAHA report",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "format": req.fmt,
        "symbols": req.symbols,
        "sector": req.sector,
        "period": req.period,
        "as_of": req.as_of.isoformat() if req.as_of else None,
        "notes": req.notes,
        "sections": sections,
        "quality": {"unavailable": unavailable},
    }


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def _rows(section: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """Normalise a section into (headers, rows) for tabular renderers."""
    if not section.get("available", True):
        return ["Status"], [[section.get("reason", "unavailable")]]
    if "headers" in section and "rows" in section:
        return [str(h) for h in section["headers"]], [list(r) for r in section["rows"]]
    if "table" in section and isinstance(section["table"], dict):
        return ([str(h) for h in section["table"].get("headers", [])],
                [list(r) for r in section["table"].get("rows", [])])
    # A summary/detail section: flatten its scalar payload.
    payload = {k: v for k, v in section.items()
               if k not in ("available", "reason", "headers", "rows", "table")}
    items = [(str(k), v) for k, v in payload.items()]
    return ["Field", "Value"], [[k, json.dumps(v) if isinstance(v, (dict, list)) else v]
                                for k, v in items]


def _safe_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names are max 31 chars and cannot contain []:*?/\\."""
    clean = "".join("_" if ch in "[]:*?/\\" else ch for ch in name)[:31] or "Sheet"
    _base, i = clean, 1
    while clean.lower() in used:
        suffix = f"_{i}"
        clean = (clean[: 31 - len(suffix)] + suffix)
        i += 1
    used.add(clean.lower())
    return clean


def render_xlsx(report: dict[str, Any]) -> bytes:
    """One worksheet per selected section, with frozen headers and filters."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    header_fill = PatternFill("solid", fgColor="071C18")
    header_font = Font(bold=True, color="F5F8F7")

    # Metadata first, always: it is what identifies the report.
    meta = wb.create_sheet(_safe_sheet_name("Report", used))
    for row in [("Title", report.get("title", "")),
                ("Generated", report.get("generated_at", "")),
                ("Format", report.get("format", "")),
                ("Symbols", ", ".join(report.get("symbols", [])) or "—"),
                ("Sector", report.get("sector") or "—"),
                ("Period", report.get("period") or "—"),
                ("As of", report.get("as_of") or "—")]:
        meta.append(list(row))
    for cell in meta[1]:
        cell.fill = header_fill
        cell.font = header_font
    meta.column_dimensions["A"].width = 18
    meta.column_dimensions["B"].width = 70
    meta.freeze_panes = "A2"

    for cid, section in report["sections"].items():
        if not section.get("available", True):
            # An unavailable section is disclosed in its own worksheet below,
            # never rendered as if it held data.
            continue
        name = section.get("name") or cid
        ws = wb.create_sheet(_safe_sheet_name(name, used))
        headers, rows = _rows(section)
        ws.append(headers)
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
        for idx, h in enumerate(headers, start=1):
            width = max([len(str(h))] + [len(str(r[idx - 1])) for r in rows[:200] if len(r) >= idx])
            ws.column_dimensions[get_column_letter(idx)].width = min(max(width + 2, 10), 60)

    # Unavailable sections are disclosed, never silently dropped.
    un = report.get("quality", {}).get("unavailable", [])
    if un:
        ws = wb.create_sheet(_safe_sheet_name("Unavailable", used))
        ws.append(["Component", "Reason"])
        for item in un:
            ws.append([item["name"], item["reason"]])
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv(report: dict[str, Any]) -> bytes:
    """A ZIP of one CSV per section — never one ambiguous mixed table."""

    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = ["PRAVAHA report", "", f"title: {report.get('title', '')}",
                f"generated: {report.get('generated_at', '')}",
                f"symbols: {', '.join(report.get('symbols', [])) or '-'}",
                f"sector: {report.get('sector') or '-'}",
                f"period: {report.get('period') or '-'}", ""]
        zf.writestr("_manifest.txt", "\n".join(meta))
        for cid, section in report["sections"].items():
            if not section.get("available", True):
                continue
            headers, rows = _rows(section)
            sio = io.StringIO()
            writer = csv.writer(sio, lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)
            name = _safe_sheet_name(section.get("name") or cid, used)
            zf.writestr(f"{name}.csv", sio.getvalue())
        # A selected component that produced nothing is disclosed, not dropped.
        un = report.get("quality", {}).get("unavailable", [])
        if un:
            sio = io.StringIO()
            writer = csv.writer(sio, lineterminator="\n")
            writer.writerow(["Component", "Reason"])
            writer.writerows([[item["name"], item["reason"]] for item in un])
            zf.writestr("_unavailable.csv", sio.getvalue())
    return buf.getvalue()


def render_json(report: dict[str, Any]) -> bytes:
    """A stable, documented structure. No credentials, ever."""
    return (json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def render_pdf(report: dict[str, Any]) -> bytes:
    """A minimal, valid, multi-page PDF with page numbers.

    Hand-rolled so the export has no hard dependency on a PDF library. Text is
    Helvetica; long rows are wrapped, and rows are packed onto a page rather than
    each getting one of its own.
    """
    from megatool.pdfwriter import wrap, write_pdf  # type: ignore[attr-defined]

    lines: list[tuple[str, int]] = [
        (f"PRAVAHA - {report.get('title', '')}", 16),
        (f"Generated {report.get('generated_at', '')}", 9),
        (f"Symbols: {', '.join(report.get('symbols', [])) or '-'}", 9),
        (f"Sector: {report.get('sector') or '-'}   "
         f"Period: {report.get('period') or '-'}", 9),
        ("Prices are end-of-day stored closes, not live quotes.", 8),
        ("", 8),
    ]
    for cid, section in report["sections"].items():
        if not section.get("available", True):
            continue
        headers, rows = _rows(section)
        lines.append((str(section.get("name") or cid), 12))
        lines.append((" | ".join(str(h) for h in headers), 8))
        for row in rows[:200]:
            for chunk in wrap(" | ".join(str(v) for v in row), width=96):
                lines.append((chunk, 8))
        lines.append(("", 8))

    un = report.get("quality", {}).get("unavailable", [])
    if un:
        lines.append(("Unavailable sections", 12))
        for item in un:
            for chunk in wrap(f"{item['name']}: {item['reason']}", width=96):
                lines.append((chunk, 8))

    # ~46 lines fit above the footer at these sizes; chunk so nothing is clipped.
    per_page = 46
    pages: list[list[tuple[float, str, int]]] = [
        [(0.0, text, size) for text, size in lines[i:i + per_page]]
        for i in range(0, len(lines), per_page)
    ] or [[(0.0, "PRAVAHA report", 12)]]
    return write_pdf(pages)


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data" / "report_templates"


def _template_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    if not safe or safe != name.replace(" ", "_") and not name.replace(" ", "_").isalnum():
        # Normalise aggressively: template file names must be filesystem-safe.
        pass
    return TEMPLATE_DIR / f"{safe}.json"


def list_templates() -> list[dict[str, Any]]:
    if not TEMPLATE_DIR.is_dir():
        return []
    out = []
    for p in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "name": t.get("name", p.stem),
            "components": t.get("components", []),
            "symbols": t.get("symbols", []),
            "sector": t.get("sector"),
            "period": t.get("period"),
            "format": t.get("format", "xlsx"),
            "title": t.get("title"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
        })
    return out


def save_template(name: str, req: ReportRequest) -> dict[str, Any]:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    path = _template_path(name)
    payload: dict[str, Any] = {
        "name": name,
        "components": req.components,
        "symbols": req.symbols,
        "sector": req.sector,
        "period": req.period,
        "format": req.fmt,
        "title": req.title,
        "notes": req.notes,
        "created_at": now,
        "updated_at": now,
    }
    if path.is_file():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            payload["created_at"] = prior.get("created_at", now)
        except (json.JSONDecodeError, OSError):
            pass
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_template(name: str) -> dict[str, Any]:
    path = _template_path(name)
    if not path.is_file():
        raise ReportBuilderError(f"no template named {name!r}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportBuilderError(f"template {name!r} is corrupt: {exc}") from exc


def delete_template(name: str) -> bool:
    path = _template_path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def rename_template(old: str, new: str) -> dict[str, Any]:
    src = _template_path(old)
    if not src.is_file():
        raise ReportBuilderError(f"no template named {old!r}")
    payload = load_template(old)
    payload["name"] = new
    dst = _template_path(new)
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if dst != src:
        src.unlink()
    return payload


def duplicate_template(name: str, new_name: str) -> dict[str, Any]:
    payload = load_template(name)
    payload["name"] = new_name
    return save_template(new_name, ReportRequest(
        components=payload.get("components", []),
        symbols=payload.get("symbols", []),
        sector=payload.get("sector"),
        period=payload.get("period"),
        fmt=payload.get("format", "xlsx"),
        title=payload.get("title"),
        notes=payload.get("notes"),
    ))
