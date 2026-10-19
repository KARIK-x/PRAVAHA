# Mega Tool design system (v2)

Derived from the reference collection (§ families in `REFERENCE_INVENTORY.md`).
The references are a **dark, dense, chart-first** terminal (NEPSE Alpha). Mega Tool
keeps the dark theme but fixes the specific problems the current screenshots show:
flat hierarchy, too many equal-weight cards, crowded toolbars, and overlapping
chart annotations.

## Layout

- **Left sidebar (fixed, 224 px)** — grouped destinations, like the reference rail.
  Grouped, not flat; the current 13-item top bar is replaced.
- **Top bar (56 px)** — brand, global symbol search, data-freshness chip,
  command hint. The search drives the shared `symbol-input` so every view follows
  one selection.
- **Content canvas** — max-width free, 20 px gutters, 16 px vertical rhythm.
- **Right rail (optional, collapsible)** — analysis/tool context (indicator
  browser, overlay manager, methodology). Mirrors the references' right column.

## Colour (dark, higher contrast than today)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0d1117` | app background |
| `--surface` | `#121821` | panels |
| `--surface-2` | `#18202b` | raised/inner |
| `--line` | `#232c39` | hairlines only (never heavy borders) |
| `--txt` | `#e6edf3` | primary text |
| `--muted` | `#8b98a9` | secondary |
| `--accent` | `#2f81f7` | interactive |
| `--up` | `#26a69a` | gains |
| `--down` | `#ef5350` | losses |
| `--warn` | `#d29922` | delayed/stale |

Status colours are **calm**: a delayed feed is `--warn` text on a translucent chip,
never a red alarm. Red is reserved for losses/invalid data.

## Typography

- UI: system stack. Numerals: `font-variant-numeric: tabular-nums` everywhere.
- Scale: 11 (label) / 12 (hint) / 13 (body) / 15 (emphasis) / 20 (stat) / 28 (hero).
- Labels are uppercase, letter-spaced `.04em`, muted — matching the references.

## Components

- **Panel** — `--surface`, 1 px `--line`, radius 10, padding 14–18. Used instead of
  many bordered mini-cards.
- **Stat** — label + tabular value; a `stat-strip` groups them in one panel.
- **Chip/Badge** — pill with translucent background; drives freshness
  (`LIVE_VERIFIED`/`DELAYED`/`STALE`/`HISTORICAL`) and status.
- **Tabs** — underline style, used to group sub-tools (references use category tabs).
- **Table** — sticky header, hairline rows, right-aligned numerics, `.click` rows.
- **Drawer** — right-side slide-in for the indicator browser / overlay manager.
- **Toolbar** — compact icon clusters with tooltips, grouped; advanced items in
  menus/drawers, never all inline.

## States

- **Empty** — short sentence + the reason, never a bare "No data".
- **Loading** — inline skeleton/hint, never a permanent "Loading…".
- **Error** — `.error` text naming the failure.
- **Unavailable** — explicit "unavailable" + why (never a fabricated `0`).

## Motion

150 ms ease on hover/drawer/tab transitions; a 600 ms one-shot highlight on a
price refresh. `@media (prefers-reduced-motion: reduce)` disables all of it.
No animation on charts while panning/zooming.

## Charts

- Candles + volume default; zoom/pan/crosshair; tabular OHLC readout.
- **Clean by default**: only the series and volume. Every overlay (S/R zones,
  Fibonacci, patterns, swings) is **off until enabled**, grouped in an **overlay
  manager**, with a per-overlay count so the user sees the cost before enabling.
- Annotation density rules: cluster levels within 0.6 % into one labelled band,
  cap labels per pane, never draw a label that overlaps another.
