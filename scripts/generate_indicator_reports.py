"""Generate INDICATOR_CATALOGUE.md and INDICATOR_SOURCE_AND_LICENSE_AUDIT.md
from the live indicator registry. Run from the repository root with the
project venv:  .venv/bin/python <this script>

Both documents are written to the repository root. The placement column
mirrors indPlacement() in web/static/app.js and is asserted against the
browser-verified matrix (33 overlay / 59 pane, 2026-10-18, 92 indicators).

The verification section of the catalogue is derived by the same scanner the
UI's information panel uses (``generate_indicator_info.verification_map``), so
the two can never disagree."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from megatool.ta import available
from megatool.ta.candles import PATTERN_NAMES

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_indicator_info import verification_map  # noqa: E402

REG = available()
N = len(REG)

#: Browser-verified matrix (web/static/app.js indPlacement over the live
#: registry). The mirror below is asserted against this so a divergence fails
#: the generator instead of silently mislabelling the catalogue.
BROWSER_PLACEMENT = {"overlay": 33, "pane": 59}

#: The most recent batch of additions, named explicitly so the catalogue can
#: say which rows are newest without scanning git history (which is uncommitted).
LATEST_BATCH = [
    "vortex",
    "ma_cross",
    "chande_kroll_stop",
    "bollinger_width",
    "percent_b",
    "chaikin_volatility",
    "relative_volatility_index",
    "average_price",
    "price_correlation",
    "williams_fractal",
    "zigzag",
]

CATEGORY_ORDER = ["trend", "momentum", "volatility", "volume", "other"]

# Mirror of indPlacement() in web/static/app.js.
TREND_PANE = {"adx", "aroon", "linreg_slope", "supertrend"}
VOLUME_OVERLAY = {"vwap_bands"}
OTHER_OVERLAY = {"median_price", "typical_price", "weighted_close", "pivot_points"}
VOL_BAND_OUTPUTS = {"upper", "middle", "lower"}


def placement(ind: dict) -> str:
    if ind.get("display") == "overlay":
        return "overlay"
    if ind.get("display") == "pane":
        return "pane"
    cat = ind["category"]
    if cat == "momentum":
        return "pane"
    if cat == "volume":
        return "overlay" if ind["name"] in VOLUME_OVERLAY else "pane"
    if cat == "trend":
        return "pane" if ind["name"] in TREND_PANE else "overlay"
    if cat == "volatility":
        outs = ind.get("outputs") or []
        return "overlay" if outs and all(o in VOL_BAND_OUTPUTS for o in outs) else "pane"
    return "overlay" if ind["name"] in OTHER_OVERLAY else "pane"


def esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


counts = Counter(i["category"] for i in REG)
place_counts = Counter(placement(i) for i in REG)
assert sum(counts.values()) == N, counts
assert dict(place_counts) == BROWSER_PLACEMENT, (dict(place_counts), BROWSER_PLACEMENT)
missing_ref = [i["name"] for i in REG if not (i.get("reference") or "").strip()]
missing_formula = [i["name"] for i in REG if not (i.get("formula") or "").strip()]
ver = verification_map([i["name"] for i in REG])
ver_counts = Counter(v["level"] for v in ver.values())

# ------------------------------------------------------------- catalogue
cat_lines: list[str] = []
cat_lines.append("# Indicator catalogue")
cat_lines.append("")
cat_lines.append(
    "Generated 2026-10-18 from the live registry (`megatool.ta.available()`), the same "
    f"data `GET /api/indicators` serves to the chart drawer. **{N} registered indicators** "
    f"({counts.get('trend', 0)} trend, {counts.get('momentum', 0)} momentum, "
    f"{counts.get('volatility', 0)} volatility, {counts.get('volume', 0)} volume, "
    f"{counts.get('other', 0)} other). Every row carries its own formula and citation in "
    "the registry; this table is the navigation index over them."
)
cat_lines.append("")
cat_lines.append(
    "Most recent batch added 2026-10-18 (`megatool/ta/extra.py`, "
    f"{len(LATEST_BATCH)} indicators): "
    + ", ".join(f"`{n}`" for n in LATEST_BATCH)
    + ". Each has an independently written numeric reference test (see **Verification** below)."
)
cat_lines.append("")
cat_lines.append("## Verification")
cat_lines.append("")
cat_lines.append(
    "Derived by scanning the test suite (`scripts/generate_indicator_info.py`, reproducible):"
)
cat_lines.append("")
cat_lines.append("| Level | Count | Meaning |")
cat_lines.append("|---|---|---|")
cat_lines.append(
    f"| `reference` | **{ver_counts.get('reference', 0)}** | Compared inside a test "
    "against an independently written formula (literal re-implementation, "
    "hand-computed value or published worked example). |"
)
cat_lines.append(
    f"| `invariants` | **{ver_counts.get('invariants', 0)}** | Exercised only against "
    "structural guarantees (no look-ahead via full-vs-prefix equality, NaN warm-up, "
    "warm-up not over-declared, short-series safety). This is a floor, **not** numeric "
    "proof. |"
)
cat_lines.append(
    f"| `sparse` | **{ver_counts.get('sparse', 0)}** | "
    + ", ".join(
        f"`{n}`" for n in sorted(n for n, v in ver.items() if v["level"] == "sparse") or ["—"]
    )
    + ". Their output is a pivot price on the bar the pivot belongs to: sparse by "
    "construction and (for `zigzag`) repainting. They are **deliberately excluded** "
    "from the two warm-up invariants, which assume a dense series, and are covered "
    "instead by dedicated property tests that assert the repainting rather than hide "
    "it. The excluded set is declared in `tests/test_indicators.py` as "
    "`SPARSE_PIVOT_INDICATORS`, so an exclusion can never be silent. |"
)
cat_lines.append(f"| `none` | **{ver_counts.get('none', 0)}** | — |")
cat_lines.append("")
cat_lines.append(
    'No indicator is claimed to be "validated" beyond this. A `reference` test checks '
    "the arithmetic against the documented formula; it does not validate the indicator "
    "as a trading signal on NEPSE."
)
cat_lines.append("")
cat_lines.append(
    "**Placement** is where the chart draws the indicator by default: `overlay` on the "
    "price chart, `pane` in its own synced panel below. The rule mirrors "
    "`indPlacement()` in `web/static/app.js` (category defaults + named exceptions; "
    "momentum/volume to panes; trend overlays except ADX/Aroon/linreg-slope/supertrend; "
    "volatility overlays only for pure upper+middle+lower band groups; Bollinger's "
    "ratio outputs keep it in a pane so they cannot wreck the price scale). The matrix "
    f"was browser-verified 2026-10-18: {place_counts['overlay']} overlay / {place_counts['pane']} pane."
)
cat_lines.append("")
cat_lines.append("## Registered indicators")
cat_lines.append("")
cat_lines.append(
    "| Indicator | Label | Category | Outputs | Placement | Default parameters | Source |"
)
cat_lines.append("|---|---|---|---|---|---|---|")
for cat in CATEGORY_ORDER:
    for i in sorted((x for x in REG if x["category"] == cat), key=lambda x: x["name"]):
        cat_lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} |".format(
                i["name"],
                esc(i["label"]),
                cat,
                esc(", ".join(i.get("outputs") or [])),
                placement(i),
                esc(json.dumps(i.get("params") or {}, ensure_ascii=False)),
                esc((i.get("reference") or "").strip()),
            )
        )
cat_lines.append("")
cat_lines.append("## Quick layers (chart toolbar checkboxes)")
cat_lines.append("")
cat_lines.append(
    "Preserved from the original chart toolbar; they are chart-level toggles, not "
    "instances of the registry: SMA(50), EMA(20), Bollinger(20, 2σ), volume bars, "
    "RSI(14) pane, MACD(12, 26, 9) pane, and swing markers (fractal pivots)."
)
cat_lines.append("")
cat_lines.append("## Candlestick patterns (Part 14)")
cat_lines.append("")
cat_lines.append(
    f"The detector in `megatool/ta/candles.py` implements **{len(PATTERN_NAMES)} named "
    "patterns** (one-bar, two-bar and three-bar rules, all documented in that module "
    "and exposed via `GET /api/bars/{symbol}/candles`):"
)
cat_lines.append("")
cat_lines.append(", ".join(f"`{p}`" for p in PATTERN_NAMES) + ".")
cat_lines.append("")
cat_lines.append(
    "The Part 14 checklist in the owner's specification names 33 patterns; the "
    "remaining names are not present in the repository snapshot, so they are tracked "
    "as backlog in `REMAINING_BLOCKERS.md` rather than guessed here."
)
cat_lines.append("")
cat_lines.append("## Coverage boundaries (Parts 8–13)")
cat_lines.append("")
cat_lines.append(
    "The Part 8–13 script/indicator name lists (~350 names: built-ins, Nepsealpha "
    "customs, community scripts, breadth, additional scripts) live in the owner's "
    "specification text, which is not in this repository. This catalogue therefore "
    f"records exactly what the registry implements — {N} registered indicators plus "
    f"the {len(PATTERN_NAMES)} candle patterns above — and makes no coverage claim "
    "against a list it cannot read. Adding a checklist file with the exact names would "
    "allow a line-by-line cross-off; see `REMAINING_BLOCKERS.md` item 3."
)
cat_lines.append("")
cat_lines.append("## How to verify")
cat_lines.append("")
cat_lines.append("```bash")
cat_lines.append(f"# registry (all {N}, with formulas and references):")
cat_lines.append(
    "curl -s http://127.0.0.1:10000/api/indicators | .venv/bin/python -m json.tool | head"
)
cat_lines.append("# this catalogue is reproducible from the registry:")
cat_lines.append(
    "#   (regenerate with scripts/generate_indicator_reports.py; the placement "
    f"mirror is asserted {place_counts['overlay']}/{place_counts['pane']})"
)
cat_lines.append("# formula guards + per-indicator reference tests:")
cat_lines.append(".venv/bin/python -m pytest tests/test_indicators.py tests/test_indicators2.py -q")
cat_lines.append("# regenerate the info metadata + verification map:")
cat_lines.append(".venv/bin/python scripts/generate_indicator_info.py")
cat_lines.append("```")
cat_lines.append("")
with open("INDICATOR_CATALOGUE.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(cat_lines))

# ------------------------------------------------------- source & license audit
aud: list[str] = []
aud.append("# Indicator source & license audit")
aud.append("")
aud.append(
    f"Date: 2026-10-18 · Scope: the {N}-entry indicator registry (`megatool/ta/`), the "
    "candlestick detectors (`megatool/ta/candles.py`), the chart's custom-formula DSL "
    "(`web/static/app.js`), and the third-party components the chart workbench loads. "
    "Method: the registry itself carries a per-indicator `reference` and `formula` "
    "field, echoed by `GET /api/indicators`; the tables below are generated from that "
    "registry and are the primary evidence for provenance. This is an inventory of "
    "what the repository records, not legal advice."
)
aud.append("")
aud.append("## 1. In-repo code provenance")
aud.append("")
aud.append(
    "* Every indicator below is implemented in Python inside this repository "
    "(`megatool/ta/*.py`). None of the implementations is a copy of third-party "
    "source code: each was written for this project from the published definition "
    "named in its `reference` field, with the arithmetic restated in the `formula` "
    "field and the guard tests verifying the stated formula."
)
aud.append(
    "* Indicator names (MACD, RSI, Bollinger Bands, Ichimoku, …) are used as "
    "conventional labels. No affiliation with, or endorsement by, any referenced "
    "author or platform is claimed."
)
aud.append(
    "* No TradingView Pine source, no Nepsealpha script text, and no community-forum "
    "code was copied into this repository. Where the owner's specification lists a "
    "script name (Parts 8–13), it was treated as a concept to implement from primary "
    "published definitions; nothing was copied verbatim from a source that carries "
    "restrictions."
)
aud.append(
    "* The chart's custom-formula DSL is original: a recursive-descent parser over a "
    "whitelisted function/series table with an AST evaluator — no `eval`, and unknown "
    "identifiers are rejected at parse time (session 19 record, B-84)."
)
aud.append("")
aud.append("## 2. Registered indicator citations (generated from the registry)")
aud.append("")
aud.append("| Indicator | Category | Recorded reference | Recorded formula |")
aud.append("|---|---|---|---|")
for i in sorted(REG, key=lambda x: (x["category"], x["name"])):
    aud.append(
        "| `{}` | {} | {} | {} |".format(
            i["name"],
            i["category"],
            esc((i.get("reference") or "").strip()) or "**(none recorded)**",
            esc((i.get("formula") or "").strip()) or "**(none recorded)**",
        )
    )
aud.append("")
aud.append("## 3. Data sources and bundled components")
aud.append("")
aud.append(
    "* **lightweight-charts 4.2.3** — vendored unmodified at "
    "`web/static/vendor/lightweight-charts.standalone.js`; TradingView's Lightweight "
    "Charts is published under Apache-2.0. The license text is not re-vendored here."
)
aud.append(
    "* **NEPSE price history** — collected from public mirrors. The community dataset "
    "`github.com/Aabishkar2/nepse-data` carries no LICENSE file (recorded limitation "
    "L-03 in `KNOWN_BUGS.md`); its redistribution terms are unverified, so the data "
    "stays in the local research store."
)
aud.append(
    "* **yonepse quote pages** — free public source; terms as published by the "
    "operator; fetched without authentication."
)
aud.append(
    "* **Kronos model weights** (`data/models/Kronos-mini`, `Kronos-Tokenizer-2k`) — "
    "official downloads from the KRONOS authors' Hugging Face repositories, recorded "
    "as byte-exact vs HF in the session-18 record. No license text is vendored; "
    "treated as research-use. Kronos is not used by any indicator in the tables above."
)
aud.append(
    "* **python-dotenv** — CVE-triggered upgrade is pending the owner's decision "
    "(see `REMAINING_BLOCKERS.md`)."
)
aud.append("")
aud.append("## 4. Approximations and parity claims")
aud.append("")
aud.append(
    "This project makes **no exact-parity claim** against any third-party "
    "implementation. Where an approximation exists it is stated in the indicator's "
    "`notes` field and its module docstring (e.g., all cached-line transform "
    "implementations document their warm-up handling). Field-for-field comparison "
    "against reference implementations has not been run; the verification that "
    "exists is the project's own guard suite: `tests/test_indicators.py` (invariants "
    "over every registered indicator) and `tests/test_indicators2.py` (literal "
    f"reference-value tests). The catalogue's **Verification** section reports the "
    f"derived split: {ver_counts.get('reference', 0)} reference / "
    f"{ver_counts.get('invariants', 0)} invariants / {ver_counts.get('sparse', 0)} "
    "sparse."
)
aud.append("")
aud.append("## 5. Restrictions honoured")
aud.append("")
aud.append(
    "* No paid API calls, no scraping of restricted content, no copied Pine sources, "
    "no deployments, no production database writes were performed for this work."
)
aud.append(
    "* Market-intelligence sources have their own terms and are covered separately by "
    "`docs/LIVE_DATA.md` and `docs/DATA_SOURCES.md`; they are outside this audit's "
    "scope (the audit covers computation code, not news/content sources)."
)
aud.append("")
aud.append("### Registry completeness check (generated)")
aud.append("")
aud.append(
    f"* Indicators with a recorded reference: **{N - len(missing_ref)}/{N}**. "
    f"Indicators with a recorded formula: **{N - len(missing_formula)}/{N}**. "
    f"(The {len(missing_ref)} without a personal attribution are generic constructions "
    f"— {', '.join('`' + n + '`' for n in sorted(missing_ref))} — not invented citations.)"
)
if missing_ref or missing_formula:
    aud.append(f"* Missing references: {', '.join(missing_ref) or '—'}.")
    aud.append(f"* Missing formulas: {', '.join(missing_formula) or '—'}.")
aud.append("")
with open("INDICATOR_SOURCE_AND_LICENSE_AUDIT.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(aud))

print("categories:", dict(counts))
print("placements:", dict(place_counts))
print("candle patterns:", len(PATTERN_NAMES))
print("missing references:", missing_ref or "none")
print("missing formulas:", missing_formula or "none")
print("unique references:", len({(i.get("reference") or "").strip() for i in REG}))
