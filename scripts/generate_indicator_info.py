"""Generate web/static/indicator_info.js from the live indicator registry.

Why this file exists
--------------------
The registry already carries the *authoritative* per-indicator metadata that the
UI needs for a documentation panel: ``label``, ``category``, ``params``,
``inputs``, ``outputs``, ``warmup``, ``reference``, ``formula`` and ``notes``.
What it does not carry is presentation/verification metadata that either (a) is
better kept out of the calculation code, or (b) can only be derived by looking
at the test suite:

* a standard abbreviation (RSI, ATR, MACD, ...),
* plain-language interpretation / limitations / "how this build differs from the
  textbook" notes,
* and the **verification status**, which is *derived by scanning the tests* so
  the UI can never claim more than the tests actually prove.

Nothing here is invented at render time: the panel reads ``formula``/``notes``/
``reference`` from the live registry and only supplements them with the fields
below. Run from the repo root:

    .venv/bin/python scripts/generate_indicator_info.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Importing the package populates the registry (each module registers on import).
import megatool.ta  # noqa: F401  (side-effect: registration)
from megatool.ta.core import _REGISTRY  # noqa: PLC2701  (internal by design)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "static" / "indicator_info.js"
TESTS = sorted((ROOT / "tests").glob("test_*.py"))

# --------------------------------------------------------------------------- #
# Curated presentation data. Short, checkable statements only.
# --------------------------------------------------------------------------- #

#: Standard abbreviations. Keyed by registry name.
ABBR = {
    "sma": "SMA",
    "ema": "EMA",
    "wma": "WMA",
    "vwma": "VWMA",
    "dema": "DEMA",
    "tema": "TEMA",
    "hma": "HMA",
    "smma": "SMMA",
    "kama": "KAMA",
    "zlema": "ZLEMA",
    "t3": "T3",
    "vidya": "VIDYA",
    "alma": "ALMA",
    "mcginley_dynamic": "MD",
    "ichimoku": "ICHIMOKU",
    "parabolic_sar": "PSAR",
    "supertrend": "SUPERTREND",
    "adx": "ADX",
    "aroon": "AROON",
    "vortex": "VI",
    "gmma": "GMMA",
    "alligator": "ALLIGATOR",
    "lsma": "LSMA",
    "linreg_slope": "SLOPE",
    "envelopes": "ENV",
    "keltner": "KC",
    "donchian": "DC",
    "bollinger": "BB",
    "bollinger_width": "BBW",
    "percent_b": "BB%B",
    "rsi": "RSI",
    "macd": "MACD",
    "stochastic": "STOCH",
    "stochastic_rsi": "STOCHRSI",
    "cci": "CCI",
    "williams_r": "WILLR",
    "roc": "ROC",
    "momentum": "MOM",
    "mfi": "MFI",
    "awesome_oscillator": "AO",
    "cmo": "CMO",
    "tsi": "TSI",
    "ultimate_oscillator": "UO",
    "fisher_transform": "FISHER",
    "kst": "KST",
    "coppock_curve": "COPPOCK",
    "connors_rsi": "CRSI",
    "rvi": "RVI",
    "balance_of_power": "BOP",
    "accelerator_oscillator": "AC",
    "smi": "SMI",
    "ppo": "PPO",
    "price_oscillator": "PO",
    "dpo": "DPO",
    "trix": "TRIX",
    "relative_volume": "RVOL",
    "volume_roc": "VROC",
    "volume_oscillator": "VO",
    "zscore": "Z",
    "standard_error": "SE",
    "atr": "ATR",
    "true_range": "TR",
    "historical_volatility": "HV",
    "choppiness": "CHOP",
    "chaikin_volatility": "CV",
    "standard_deviation": "STDEV",
    "standard_error_bands": "SEB",
    "chande_kroll_stop": "CKS",
    "garman_klass": "GK",
    "volatility_zero_trend": "VZT",
    "relative_volatility_index": "RVI-V",
    "obv": "OBV",
    "ad_line": "A/D",
    "cmf": "CMF",
    "chaikin_oscillator": "CHAIKIN",
    "klinger": "KVO",
    "force_index": "EFI",
    "ease_of_movement": "EOM",
    "pvt": "PVT",
    "net_volume": "NETVOL",
    "vwap_bands": "VWAP",
    "volume_sma": "VOL-SMA",
    "volume_profile": "VP",
    "money_flow_index": "MFI",
    "pivot_points": "PIVOT",
    "zigzag": "ZIGZAG",
    "williams_fractal": "FRACTAL",
    "mass_index": "MASS",
    "typical_price": "TP",
    "median_price": "MEDPRICE",
    "average_price": "AVGPRICE",
    "weighted_close": "WCLPRICE",
    "correlation": "CORR",
    "price_correlation": "PCORR",
    "ma_cross": "MACROSS",
}

#: Friendly names for the input columns.
INPUTS_FRIENDLY = {
    "open": "open price",
    "high": "high price",
    "low": "low price",
    "close": "close price",
    "volume": "traded volume",
}

#: Shared explanations for parameter names, so a variable is never left bare.
VARIABLES = {
    "period": "lookback length, in bars — how many observations each value averages or scans",
    "fast": "the shorter lookback (reacts faster)",
    "slow": "the longer lookback (smoother, more lag)",
    "signal": "lookback for the smoothing/signal line",
    "smooth": "lookback for the final smoothing step",
    "k": "lookback length in bars",
    "n": "lookback length in bars",
    "multiplier": "band width in ATR (or σ) multiples",
    "std_dev": "number of standard deviations for the bands",
    "atr_period": "lookback for the ATR used to size the bands",
    "atr_multiple": "band width in ATR multiples",
    "offset": "0 = oldest bars weighted most, 1 = newest bars weighted most",
    "sigma": "Gaussian width — larger is flatter/smoother",
    "tenkan": "conversion-line length (default 9)",
    "kijun": "base-line length (default 26)",
    "senkou_b": "second leading-span length (default 52)",
    "step": "SAR acceleration-factor increment",
    "maximum": "acceleration-factor ceiling",
    "tenkan_sen": "conversion-line length",
    "kijun_sen": "base-line length",
    "senkou_span_b": "second leading-span length",
    "up": "threshold above which the series is read as 'high'",
    "down": "threshold below which the series is read as 'low'",
    "percent": "band half-width as a fraction of price (0.05 = ±5%)",
    "upper": "upper threshold",
    "lower": "lower threshold",
    "window": "lookback window in bars",
    "span": "lookback window in bars",
    "bins": "number of price buckets in the profile",
    "lookback": "lookback window in bars",
    "threshold_pct": "minimum move, as a percentage, to mark a swing",
    "depth": "maximum swing depth searched",
    "trail": "second-stage trailing width in ATR multiples",
    "roc_period": "lookback used for the rate-of-change comparison",
    "ema_period": "EMA length that smooths the series before the rate of change",
    "long": "longer lookback used in the comparison (e.g. 14 bars)",
    "short": "shorter lookback used in the comparison (e.g. 11 bars)",
    "rsi_period": "lookback for the RSI inside the composite",
    "streak_period": "lookback for the up/down streak length",
    "rank_period": "lookback over which the percent-rank is computed",
    "wma_period": "lookback for the weighted moving average of the ROC sum",
    "smooth1": "first smoothing length applied to the raw momentum",
    "smooth2": "second smoothing length applied after smooth1",
    "k_period": "lookback for the %K stochastic line",
    "d_period": "lookback for the %D signal line",
    "stoch_period": "lookback for the stochastic applied to RSI",
    "medium": "medium lookback used in the composite (between short and long)",
    "jaw_period": "lookback for the Alligator jaw (slowest) line",
    "jaw_offset": "bars the jaw line is shifted into the future",
    "teeth_period": "lookback for the Alligator teeth line",
    "teeth_offset": "bars the teeth line is shifted into the future",
    "lips_period": "lookback for the Alligator lips (fastest) line",
    "lips_offset": "bars the lips line is shifted into the future",
    "volume_factor": "Tillson volume factor (0.7 is the author's default)",
    "short_period": "short EMA length used for the CMO/volatility seed",
    "annualize": "trading days per year used to annualise the volatility",
    "trading_days": "trading days per year used to annualise the volatility",
    "sum_period": "lookback over which the mass index is summed",
    "mult": "band width in standard-error multiples",
    "baseline": "lookback used to compute the baseline average volume",
}

#: "How this build differs from the textbook" — only where it genuinely does.
FORMULA_NOTES = {
    "rsi": "Wilder's smoothing (alpha = 1/period) with a simple-mean seed over the first period, exactly as in Wilder (1978) — not a plain moving average.",
    "ema": "Seeded with the SMA of the first `period` values, then recursive with alpha = 2/(period+1). Values match references once past warm-up.",
    "smma": "Identical to Wilder's smoothing (also called RMA): seed = SMA of the first period, then alpha = 1/period.",
    "atr": "True range is max(high-low, |high-prevClose|, |low-prevClose|), then Wilder-smoothed — not a simple average of ranges.",
    "adx": "Directional movement is Wilder-smoothed and DX is averaged with Wilder smoothing; +DI/-DI are ATR-normalised. Values before ~2×period are warm-up gaps.",
    "macd": "EMA(12) − EMA(26) with an EMA(9) signal; the EMAs use the shared SMA seed, so the first ~33 bars are warm-up.",
    "bollinger": "The middle band is an SMA and the width is the **population** standard deviation (ddof=0), which is the standard definition — not the sample std.",
    "ichimoku": "Senkou A/B are plotted **unshifted** (no 26-bar forward displacement). The displacement is a display convention, not information, so leaving it out avoids drawing into the future.",
    "vwma": "A rolling volume-weighted average of bar closes. It is NOT session VWAP — that needs intraday trades NEPSE daily history does not contain.",
    "vwap_bands": "This is a rolling VWAP over `period` bars with ±σ bands, not an intraday session VWAP. On the NEPSE index only turnover is owned, so the volume input is the index turnover and the figure is not a traded-share VWAP.",
    "supertrend": "ATR-based bands with a ratchet that only tightens while the trend continues; direction flips when the close crosses the band.",
    "hma": "Half-period is floored; the final smoothing length is round(sqrt(period)) — both standard Hull choices.",
    "stochastic": "%K is a raw stochastic of the close within the high/low range; the smooth variant applies an SMA.",
    "mfi": "A money-flow version of RSI: typical price × volume, Wilder-style ratios of positive to negative money flow.",
    "obv": "Running sum of signed volume, using the close-to-close sign. No volume ⇒ the indicator is not drawn (it is never filled with zero).",
    "cmf": "Money Flow Multiplier = ((close-low)-(high-close))/(high-low), volume-weighted over the period. A zero range yields a zero multiplier rather than a divide-by-zero.",
    "historical_volatility": "Standard deviation of log returns, annualised by √252 (trading days). The annualisation factor is a convention, stated here so the number is not a mystery.",
    "choppiness": "100·log10(Σ TR / (maxHigh−minLow)) / log10(period); near 100 = choppy, near 0 = trending.",
    "fisher_transform": "Recursive transform of a normalised price position, with the signal line a one-bar shift of the transform.",
    "coppock_curve": "Weighted moving average of the sum of two rate-of-change series — a long-term turning-point tool, so warm-up is long.",
    "pivot_points": "Classic floor-trader pivots from the prior bar's high/low/close; the pivot itself is the average of the three.",
    "donchian": "Highest high / lowest low channels; the middle band is their average.",
    "keltner": "EMA middle with ATR-scaled bands — the ATR version, not the original SMA/range version.",
    "standard_error_bands": "A linear-regression line with bands ±k standard errors of the regression fit — different from Bollinger, which bands the price itself.",
    "mcginley_dynamic": "First-order recursive filter with a (close/MD)^4 speed term — the author's own non-standard construction.",
    "t3": "Chain of six EMAs combined with the Tillson volume factor.",
    "kama": "Kaufman adaptive average whose smoothing constant varies with the efficiency ratio.",
    "vidya": "Volatility-index-driven average; the smoothing constant scales inversely with recent volatility.",
    "zlema": "Zero-lag EMA: the close is pre-shifted by (period−1)/2 bars, then EMA-smoothed.",
    "smi": "Stochastic momentum index over the close relative to the midpoint of a high/low range.",
    "vortex": "True range is Wilder's; the VM sums are plain window sums over `period`. No crossovers are filtered.",
    "ma_cross": 'Both averages are SIMPLE moving averages (SMA), not EMAs. The `state` column is a gap during warm-up rather than 0, so "no reading" and "flat" are not conflated.',
    "chande_kroll_stop": "Both stages are exposed: `initial_long/short` are the highest/lowest-based first stops and `stop_long/short` are the path-dependent trailing stops. ATR uses Wilder smoothing with an SMA seed.",
    "bollinger_width": "Reported in PERCENT (100 × the ratio). The Bollinger Bands indicator's `bandwidth` column is the raw ratio, so the two differ by a factor of 100.",
    "percent_b": "Uses the **population** standard deviation (ddof=0), the same convention as the Bollinger Bands indicator.",
    "chaikin_volatility": "Uses the shared SMA-seeded EMA for the smoothed high-low range, so the first `ema_period` bars are warm-up.",
    "relative_volatility_index": "Uses the **population** standard deviation (ddof=0) of the close and Wilder smoothing with a simple-mean seed — Dorsey's construction, not an RSI variant.",
    "average_price": "The mean of the bar's own open/high/low/close — not a moving average and not volume-weighted.",
    "price_correlation": "Pearson correlation of the close against the bar index, computed with population moments; it measures LINEAR trend strength only.",
    "williams_fractal": "Sparse by construction: a value appears only on a fractal bar. A fractal is knowable only `window` bars later, so the last `window` bars can still gain one.",
    "zigzag": "Sparse by construction and the final pivot is provisional until a reversal of `threshold_pct` confirms it — see the catalogue note on sparse indicators.",
    "quantity": "",
}

#: Interpretation guidance for the indicators that are read with thresholds.
INTERPRETATION = {
    "rsi": "Readings above 70 are conventionally 'overbought' and below 30 'oversold', but in a strong trend these levels persist — divergence between price and RSI or a failure swing carries more weight than the raw level.",
    "macd": "Signal-line crossovers and the zero line are the usual readings; a histogram shrinking toward zero marks a fading trend. It lags by design.",
    "bollinger": "Price riding a band signals trending strength, not reversal; contraction (low width) precedes expansion. A close outside the band is a stretch, not a signal by itself.",
    "supertrend": "The line flips sides and acts as a trailing stop; it gives many whipsaws in sideways markets because it is an ATR trend tool.",
    "atr": "Read it as a volatility unit, not a direction. Position sizing and stop distance are its main uses (this tool uses it for band width).",
    "adx": "Above ~25 is the usual 'trending' reading and below ~20 'range-bound'; the direction comes from +DI vs −DI, not the ADX level itself.",
    "stochastic": "Above 80 / below 20 are the conventional extremes; crossovers within those zones and divergence from price are the standard uses.",
    "cci": "Above +100 / below −100 mark strong deviation from the average; the classic use is divergence and zero-line crosses.",
    "williams_r": "Scaled −100…0: above −20 is 'overbought', below −80 'oversold'. It is an inverted stochastic and carries the same caveats.",
    "mfi": "A volume-weighted RSI: above 80 / below 20 are the money-flow extremes, and divergence is read as a money-flow warning.",
    "obv": "Read the slope and divergence from price; the absolute level is arbitrary because it depends on where the series starts.",
    "cmf": "Positive = net buying pressure over the window, negative = net selling. It is an oscillator around zero, not a level.",
    "historical_volatility": "Compared against its own history; a spike marks realised-risk expansion. It says nothing about direction.",
    "choppiness": "High values = sideways/choppy, low values = trending. It is a regime filter, not a timing signal.",
    "awesome_oscillator": "Reads the difference between short and long momentum; zero-line crosses and 'saucer' shapes are the usual signals.",
    "fisher_transform": "Sharp turns at extremes are the point; it is designed to mark turning points earlier, at the cost of more noise.",
    "balance_of_power": "Measures where the bar closed within its range: consistently positive = buyers in control. It is a per-bar reading usually smoothed by eye.",
    "aroon": "Above 70/ below 30 mark how recently the extremes were set; Aroon-Up crossing Aroon-Down is the trend-change cue.",
    "ichimoku": "Price above the cloud = bullish context; the cloud's thickness reads as support/resistance. It is a context tool with layered components.",
    "parabolic_sar": "Acts as a trailing stop that accelerates; it reverses a lot in ranges and is best combined with a trend filter.",
    "donchian": "A break of the upper/lower channel marks a new N-bar extreme — the basis of turtle-style breakout logic.",
    "keltner": "Trend-following envelope: price closing outside a band with a rising EMA reads as a breakout rather than a mean-reversion stretch.",
    "cmf_": "",
    "hma": "The point is low lag: its crossings with price turn earlier than an SMA of the same nominal length, at some cost in smoothness.",
    "standard_deviation": "A pure volatility reading in price units; rising = wider bar-to-bar dispersion.",
}

#: Known limitations, stated honestly. Only where they genuinely apply.
LIMITATIONS = {
    "bollinger": "Assumes roughly normal dispersion; the bands are symmetric and lag a persistent trend.",
    "rsi": "In a long one-way trend RSI can sit at an extreme for weeks, so the fixed 70/30 levels are context-dependent.",
    "macd": "Two EMAs make it lag at turning points; the absolute value scales with price.",
    "atr": "Direction-blind; it rises on gap-and-fade bars just as much as on clean trends.",
    "adx": "Lag is intrinsic (double smoothing); it turns up only after a trend is already moving.",
    "vwma": "Needs real volume; the NEPSE index only owns turnover, so it is skipped there rather than approximated.",
    "obv": "The starting level is arbitrary and the close-to-close sign ignores intrabar gyrations.",
    "mfi": "Needs volume and typical price; it is undefined on a zero-range bar and is skipped rather than zero-filled.",
    "hv": "Annualising with √252 assumes returns are independent and identically distributed; real NEPSE returns cluster.",
    "historical_volatility": "√252 annualisation assumes independent, identically distributed returns; real returns cluster and gap.",
    "ichimoku": "The many lines make it slow for short timeframes; without the standard 26-bar displacement the visual differs from most textbooks.",
    "supertrend": "Whipsaws heavily in ranges — by far its weakest regime.",
    "pivot_points": "Only meaningful when the prior bar is a genuine completed session; on a gap-up open, the computed levels are reference points, not guarantees.",
    "parabolic_sar": "Sharp reversals in choppy markets; needs a filter.",
    "choppiness": "A lagging regime descriptor — it tells you which regime you were in, not when it changes.",
    "standard_deviation": "In price units, so it is not comparable across symbols with different price scales.",
    "mcginley_dynamic": "The fourth-power speed term makes it react non-linearly; parameter choice is author-specific.",
    "kama": "Adaptive window means behaviour differs markedly in trending vs ranging phases, which can surprise users.",
    "pivot_points_": "",
    "ease_of_movement": "Scales with volume and price units, so its absolute value is only comparable within one symbol.",
    "net_volume": "Uses signed volume from the close-to-close sign; it is not exchange-reported net flow.",
    "klinger": "Long warm-up (34/55) and needs volume; short histories give mostly NaN.",
    "vortex": "Both lines hover around 1.0 and cross frequently, so a crossover alone is noisy and is not a trade signal.",
    "ma_cross": "Whipsaws badly in sideways markets; the crossover lags by construction and the SMA pair is not optimised for any symbol.",
    "chande_kroll_stop": "Path-dependent: the trailing stop depends on where the calculation window begins, so two charts with different start dates can differ.",
    "chaikin_volatility": "Direction-blind — it measures range expansion, not direction, and uses an SMA-seeded EMA that lags.",
    "relative_volatility_index": "The 50 threshold is Dorsey's published convention, not something validated on NEPSE; it also rises on large moves in either direction.",
    "price_correlation": "Only linear dependence is measured; a strong non-linear trend can read as near-zero, and it assumes a gap-free bar index.",
    "average_price": "A per-bar mean, so it inherits the bar's noise; it is not a tradable level.",
    "bollinger_width": "No fixed squeeze threshold is asserted — 'narrow' is only meaningful relative to the same symbol's own history.",
    "percent_b": "Undefined when the bands collapse (upper == lower); those bars are gaps, not 0.",
    "williams_fractal": "Fractals are common and noisy on their own and confirm late; use only inside a broader structure.",
    "zigzag": "REPAINTS: the last pivot moves as new bars arrive, so it cannot be used as a real-time signal, and the threshold choice is arbitrary.",
    "chande_kroll_stop_": "",
}

NUMERIC_HINT = re.compile(
    r"literal|exact|hand[-_ ]?comput|published|matches_(?:literal|wilder|numpy)|naive|reference",
    re.IGNORECASE,
)

#: The tests that exercise EVERY registered (dense) indicator. Named explicitly
#: rather than detected from block text, so adding a naive helper next to a
#: parametrised test can never silently promote the whole registry to
#: "reference".
INVARIANT_TESTS = {
    "test_no_lookahead_full_series_equals_prefix",
    "test_warmup_is_nan",
    "test_warmup_is_not_over_declared",
    "test_short_series_does_not_crash",
}


def verification_map(names: list[str]) -> dict[str, dict[str, str]]:
    """Derive per-indicator verification from the test suite.

    Three honest levels:

    * ``reference`` — the indicator is compared, inside a test, against an
      independently written formula: a literal re-implementation (``_naive_*``),
      a hand-computed value, or a published worked example. Detected by the test
      function name matching NUMERIC_HINT **or** the block defining a naive
      reference implementation.
    * ``invariants`` — the indicator is exercised, but only against structural
      guarantees (no look-ahead via full-vs-prefix equality, NaN warm-up, warm-up
      not over-declared, short-series safety). The global
      ``@pytest.mark.parametrize("name", ALL_INDICATORS)`` tests cover every
      registered indicator, so this is the floor, never a claim of numeric proof.
    * ``sparse`` — the indicator emits a sparse pivot series (a value on the bar
      the pivot belongs to) and is therefore deliberately excluded from the
      warm-up/no-look-ahead invariants, which assume a dense series. It is
      covered instead by dedicated property tests, and its repainting is
      asserted rather than hidden. The set is declared in the test module as
      ``SPARSE_PIVOT_INDICATORS`` so an exclusion can never be silent.

    This deliberately never upgrades an indicator to ``reference`` just because a
    test mentions its name.
    """

    out = {n: {"level": "none", "where": ""} for n in names}
    compute_re = re.compile(r'compute\(\s*"([a-z0-9_]+)"')
    tuple_re = re.compile(r'\(\s*"([a-z0-9_]+)"\s*,')
    sparse_re = re.compile(r"SPARSE_PIVOT_INDICATORS\s*=\s*\{([^}]*)\}")
    sparse: set[str] = set()
    for path in TESTS:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in sparse_re.finditer(text):
            sparse |= set(re.findall(r'"([a-z0-9_]+)"', m.group(1)))
        # Keep each decorator with its test so a parametrize list counts.
        blocks = re.split(r"\n(?=@pytest|def test_)", text)
        for block in blocks:
            m = re.search(r"def (test_[A-Za-z0-9_]+)", block)
            if not m:
                continue
            fn = m.group(1)
            numeric = bool(NUMERIC_HINT.search(fn)) or "_naive_" in block
            covered = set(compute_re.findall(block)) | set(tuple_re.findall(block))
            if fn in INVARIANT_TESTS:
                covered = set(names)
                numeric = False  # the invariant floor is coverage, never proof
            for name in covered:
                if name not in out:
                    continue
                level = "reference" if numeric else "invariants"
                # A numeric (reference) test always promotes, even over an
                # earlier invariant-only result; an invariant test only fills a
                # gap, never downgrades a reference result.
                if level == "reference":
                    out[name] = {"level": level, "where": f"{path.name}::{fn}"}
                elif out[name]["level"] == "none":
                    out[name] = {"level": level, "where": f"{path.name}::{fn}"}
    for name in sparse:
        if name in out:
            out[name] = {
                "level": "sparse",
                "where": "tests/test_indicators.py::test_sparse_pivot_output_is_sparse_and_on_real_prices",
            }
    return out


def main() -> None:
    names = sorted(_REGISTRY)
    ver = verification_map(names)
    info: dict[str, dict] = {}
    for name in names:
        meta, _fn = _REGISTRY[name]
        d = meta.describe()
        params = d["params"] or {}
        entry = {
            "name": name,
            "label": d["label"],
            "abbr": ABBR.get(name, d["label"]),
            "category": d["category"],
            "outputs": d["outputs"],
            "warmup": d["warmup"],
            "output_warmup": d["output_warmup"],
            "reference": d["reference"],
            "formula": d["formula"],
            "notes": d["notes"],
            "display": d["display"],
            "inputs": d["inputs"],
            "inputs_friendly": [INPUTS_FRIENDLY.get(i, i) for i in d["inputs"]],
            "variables": [[k, VARIABLES.get(k, "")] for k in params],
            "formula_note": FORMULA_NOTES.get(name, ""),
            "interpretation": INTERPRETATION.get(name, ""),
            "limitations": LIMITATIONS.get(name, ""),
            "verification": ver[name]["level"],
            "verification_where": ver[name]["where"],
        }
        info[name] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(info, indent=1, sort_keys=True)
    OUT.write_text(
        "/* GENERATED by scripts/generate_indicator_info.py — do not edit by hand.\n"
        "   Presentation + verification metadata for the indicator documentation\n"
        "   panel. Calculation truth lives in the Python registry; this file only\n"
        "   adds abbreviations, variable/limitation prose and the verification level\n"
        "   derived from the test suite. */\n"
        "window.INDICATOR_INFO = " + body + ";\n",
        encoding="utf-8",
    )
    levels: dict[str, int] = {}
    for e in info.values():
        levels[e["verification"]] = levels.get(e["verification"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)} with {len(info)} entries")
    print("verification levels:", levels)
    miss_abbr = [n for n in names if n not in ABBR]
    if miss_abbr:
        print("NOTE - no abbreviation curated for:", ", ".join(miss_abbr))


if __name__ == "__main__":
    main()
