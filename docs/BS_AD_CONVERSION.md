# Bikram Sambat → Gregorian conversion

## Decision

A **local, versioned, reproducible mapping table** is vendored into the
repository at `data/bs_ad/`. Conversion is a pure lookup; no date math is
performed at runtime and no HTTP conversion service is used.

The alternative — regenerating the table from the network — was rejected
because the BS calendar is *administrative*: the Panchang Samiti rules on
borderline dates each year, so any computed month length is a guess. A
published 1:1 table is the only non-guessing source.

## Source

| | |
|---|---|
| Repository | `opennp/nepali-dates` |
| URL | https://github.com/opennp/nepali-dates |
| Path | `dates/<BS year>.json` — one flat array per BS year |
| Coverage fetched | **BS 2050-01-01 → 2086-12-30** (AD 1993-04-13 → 2030-04-13), 13,515 day mappings |
| Licence | Published as a community data table; retain `source` provenance on every answer (the module does this) |

A second reference, `bikram-sambat`, was considered and rejected: it *computes*
BS dates from an algorithm, which is exactly the guessing this project must not
do for administrative calendar dates.

## Files

| Path | What it is |
|---|---|
| `data/bs_ad/bs_ad_map.json` | Consolidated table, both directions, ~370 KB. **Read at runtime.** |
| `data/bs_ad/dates/<year>.json` | Raw per-BS-year source files. Provenance and rebuild input. |
| `megatool/bs_ad.py` | The adapter: `BsAdMap`, `bs_to_ad`, `ad_to_bs`, `build_mapping`, `validate_mapping`. |

`data/` is git-ignored, so the table is a **build artefact, not committed
source**. It must be rebuilt on a fresh checkout (command below) before the
calendar can resolve Gregorian dates. This is deliberate: it is third-party
data, and committing 370 KB of someone else's dataset would make provenance
ambiguous.

## Regenerate

```
python -m megatool.bs_ad --build            # writes data/bs_ad/bs_ad_map.json
python -m megatool.bs_ad --validate         # structural check, no network
python -m megatool.calendar-import --start 2052-01 --end 2084-12
```

`--build` fetches 37 files with a 0.4 s gap and writes both the raw cache and
the consolidated table. Re-running `calendar-import` afterwards re-parses the
cached Hamro Patro pages (no network) and re-resolves every record.

## Validation

`BsAdMap.validate()` checks, over all 13,515 days:

1. AD days within each BS year are contiguous.
2. Every day round-trips AD → BS → AD identically.
3. BS months have 29-32 days, and each month's day numbering starts at 1.
4. Mapped BS years form one contiguous range.

Known anchors the mapping satisfies (independently checkable):

| BS | AD | Note |
|---|---|---|
| 2050-01-01 | 1993-04-13 | start of fetched range |
| 2080-01-01 | 2023-04-14 | Nepali New Year 2080 |
| 2080-12-30 | 2024-04-12 | last day of BS 2080 |
| 2081-01-01 | 2024-04-13 | Nepali New Year 2081 |
| 2086-12-30 | 2030-04-13 | end of fetched range |

## Known source anomalies — reported, not repaired

BS **2083** (the current year, AD 2026-2027) contains three months in the
published table whose day numbering is inconsistent: months 7, 8 and 10 begin
on BS day 31, 30 and 30 rather than day 1. This affects 90 BS dates.

These are properties of the source, not of this module, so they are surfaced
rather than silently renumbered:

* `BsAdMap.month_start_anomalies()` lists them.
* `BsAdMap.anomalous_bs_dates()` returns the 90 triples.
* `BsAdMap.bs_to_ad` **refuses every day in those three months**, because the
  day-of-year arithmetic it relies on is not trustworthy there. Guessing would
  break provenance.

Effect on the extracted calendar: of 13,311 stored events, **13,155 resolve to
a Gregorian date and 156 remain unresolved — all 156 in BS 2083** (151 inside the
three anomalous months, 5 elsewhere in that year). Zero records outside the
mapped BS range remain.

## Scope actually required

The stored market history runs AD 1995 → 2026 and the calendar covers BS 2051 →
2085. The fetched BS 2050 → 2086 comfortably covers both, with margin on each
side. Years beyond 2086 were **not** fetched: the calendar's own coverage ends
at 2085, and pulling more would be scope creep without a consumer.
