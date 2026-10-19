# SESSION 32 — CORRECTNESS INVENTORY

For every calculation family, what its correctness rests on. "Reference" means a
hand-computed or independently derived series; "invariant" means a structural
property that must hold; "oracle" means an independent naive re-implementation.

## Indicators (92)
- 62 verified against reference series or closed-form values.
- 28 verified by invariants (range, ordering, symmetry, warm-up NaN patterns).
- 2 sparse-data maps (e.g. ZigZag/pivot) verified by structure only — a pivot is
  a local extremum, not a value that can be compared bar-by-bar.
- Independent naive oracles live in `tests/_naive_helpers.py`.

## Screening metrics (41)
- Evaluated by the real screen engine; each preset's condition tree is validated
  by `megatool.scanner.validate_tree` inside the catalogue test.

## Backtest strategies (58)
- `test_every_workshop_strategy_runs_leak_free` compiles and runs every strategy
  on synthetic bars and asserts positions contain only 0/1 and never read future
  bars. Fees, execution timing, whole-units and CGT refusal paths have dedicated
  tests.

## Analysis engines (19)
| Engine | Correctness basis |
|---|---|
| monte_carlo | seed reproducibility (identical output); percentile ordering; bootstrap uses supplied returns |
| risk_of_ruin | bounds [0,1]; monotone in risk per trade; seed reproducibility |
| efficient_frontier | weights sum to 1, non-negative; min-variance beats equal weight on a known covariance |
| hrp_portfolio | weights sum to 1, long-only; cluster order is a permutation of inputs |
| deflated_sharpe | probability in [0,1]; more trials never raise the adjusted probability |
| stress_test | refuses without a benchmark (no substitution with zero) |
| event_study | refuses without supplied dates; next-session entry |
| dcf / reverse_dcf | hand-computed per-share value; growth round-trips through reverse DCF; WACC ≤ terminal growth refused |
| liquidity_drought | refuses missing/all-zero volume; state threshold rule |
| fundamental_forensics | flags non-positive capital; refuses with no records |
| factor_snapshot | rejects unknown factors; requires a universe; long/short spread defined |
| coverage_explorer | live counts; gaps listed |
| correlation_matrix / rolling_beta | refuse with <2 symbols / unknown benchmark |
| volatility_percentile / technical_rating / mtf_confluence | bounded outputs; component breakdown |
| signal_outcomes | next-bar entry; refuses unknown signal |

## Fundamental tools (32)
- Each returns `available` + `value` or an explicit `reason`; a missing field is
  never returned as 0. Dividend yield is BLOCKED with a reason (0 DPS records).

## Property / metamorphic
- Percentile ordering, monotonicity in risk, trial-count monotonicity, simplex
  validity, benchmark-required refusal, and next-bar entry are all asserted.

## Known non-claims
- No fundamental value is imputed.
- No price is treated as adjusted.
- No result is described as a forecast.
