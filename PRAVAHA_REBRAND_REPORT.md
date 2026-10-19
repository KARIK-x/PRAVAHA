# PRAVAHA — Brand Transformation & Frontend Redesign Report

**Product identity:** PRAVAHA — NEPSE Analytics Platform
**Tagline:** Insights today. A brighter tomorrow.
**Brand essence:** Clarity through market complexity.
**Scope:** user-facing branding, design tokens, shared components, all reachable
frontend surfaces. **Backend, API contracts, analytical engines, routes and data
were not changed.**
**Date:** 2026-10-19 · **Dev:** http://127.0.0.1:10000 · **Prod `:8710`:** untouched.

---

## A. Summary of the transformation

The application already had a working, token-driven CSS architecture: eleven
`--bg/--bg2/…/--info` custom properties that the whole stylesheet, the SVG
visualisation module and the charting engine already used. Rather than fork the
appearance, the rebrand **re-pointed those tokens at the PRAVAHA palette** and
then replaced the ~120 hard-coded colours that had escaped the token system.

Concretely, three layers were applied:

1. **Token foundation** — the `:root` block in `web/static/styles.css` is now the
   full PRAVAHA design-token system (11 brand colours + derived surfaces, states,
   shadows, gradients, typography, an 8-px spacing scale, radii, motion timings).
   The eleven legacy names are kept as aliases pointing at the new tokens, so
   **not one existing selector had to be rewritten**.
2. **Colour consolidation** — every remaining literal hex/rgba in the stylesheet,
   `app.js`, `viz.js` and `kronos_ui.js` was replaced with a token or palette
   reference. `app.js` now carries a single documented `PRAVAHA` palette object;
   `viz.js` reads the CSS custom properties at runtime, so charts and chrome can
   no longer drift apart.
3. **Brand layer + shell** — the old "MT" chip was replaced by the supplied
   PRAVAHA symbol mark, the sidebar/header/footer carry the lockup and tagline,
   and a PRAVAHA brand layer at the end of the stylesheet re-skins buttons,
   inputs, tables, tabs, pills, modals, drawers, toasts, empty/error states,
   scrollbars and focus rings.

Three legacy static dashboards that were still reachable (`/dashboard.html`,
`/market_dashboard.html`, `/research.html`) displayed hard-coded, unverified
figures under old branding. They are now branded redirect stubs — the routes
still resolve (HTTP 200) but the fabricated numbers are gone.

## B. Pages and components updated

All 40 navigation destinations and 25 view sections inherit the new system,
because they are styled from the shared tokens.

| Surface | What changed |
|---|---|
| App shell (`.shell`, `.sidebar`, `.topbar`, `.nav`) | Deep-Forest bands on Obsidian, emerald active state with an inset accent bar, hover tint, compact ≤900 px horizontal nav strip preserved and re-skinned |
| Sidebar brand (`.side-brand`) | New lockup: symbol mark + PRAVAHA + "NEPSE Analytics Platform" |
| Overview dashboard | Re-tokened gauge, sector bars, turnover donut, fundamental map, heat tiles, breadth/seasonality hosts |
| Charting workspace | Chart chrome, grid, borders, crosshair, candle/volume colours, OHLCV legend, draw rail, toolbar, empty state |
| Market Scanner | Controls, result tables, pills, empty/no-match states |
| Quant Lab / Algorithm workshop | Inputs, run buttons, panes, notes |
| Strategy Lab / Backtesting | Parameter rows, metric cards, equity/drawdown/histogram series |
| Research Desk + AI assistant | Chat panel/bubbles/tools, provenance blocks, derived-vs-observed labelling styles |
| Fundamentals | Metric tables, period labels, warnings |
| Portfolio & risk | KPI cards, tables, up/down semantics |
| Market Intelligence, Floorsheet, Journal, PDF Journal, Data & Quality | Tables, banners, status text |
| KIMI Research (all 18 tabs) | Tab strip, cards, tables, charts, ⓘ modals |
| Sasto Share (7 panels) | Tabs, KPI cards, range bars, sparklines, multi-pane charts, caveats |
| Footer | PRAVAHA brand line + tagline, disclaimer and attribution retained |
| Legacy static pages (3) | Rebranded redirect stubs |
| Command palette, modals, drawers, toasts, tooltips | Re-skinned via the brand layer |

## C. Logo and asset files

The supplied artwork (`logoFimage.png`, 1254×1254) was **left intact**. Variants
were derived from it with Pillow (LANCZOS), without stretching or recolouring:

| File | Size | Use |
|---|---|---|
| `web/static/brand/pravaha-symbol.png` | 512² | symbol mark, square crop clear of the wordmark |
| `web/static/brand/pravaha-symbol-128.png` | 128² | sidebar nav mark, in-page marks |
| `web/static/brand/pravaha-symbol-64.png` | 64² | favicon (`sizes="64x64"`) |
| `web/static/brand/pravaha-appicon-192.png` | 192² | `apple-touch-icon` / app icon |
| `web/static/brand/pravaha-logo.png` | 894×~827 | full lockup (symbol + wordmark + descriptor) |
| `web/static/brand/pravaha-logo-full.png` | 1000² | complete artwork incl. tagline |

Notes and honest limitations:
- The source has a **solid gradient background (no alpha)**. A transparent
  variant was produced (border flood-fill) and **rejected**: it left a visible
  white fringe on the ribbon, which the brief forbids. No transparency hacks are
  shipped. The opaque mark sits in a rounded, bordered container on the dark
  surface instead, so nothing is keyed out, stretched or haloed.
- The favicon is the **symbol crop, not the square lockup**, per the brief.
- There is no login/authentication page, About page or loading screen in this
  application, so those slots have no target. They are recorded as N/A in §J.

## D. Main CSS / design-token changes

Brand tokens (exact values from the guide):

```
obsidian #06110F · deep-forest #071C18 · panel #102722
emerald #00D69A · mint #A8FFD9 · cyan #00D9E8
white #F5F8F7 · muted #9DB4AE · border #24453C
caution #E9C46A · risk #FF6B78
```

Derived tokens: `panel-2/panel-3` surfaces, `hover`, `focus`, `disabled`, `grid`,
`shadow`, `glow`, `signal` gradient, plus financial semantics `up #1FC98A` /
`down #FF6B78` / `flat`, typography stacks (`--font-display` Space Grotesk,
`--font-ui` Inter, `--font-mono` JetBrains Mono), an 8-px spacing scale, radii
and motion timings.

Legacy aliases preserved: `--bg --bg2 --bg3 --line --txt --muted --accent --up
--down --warn --info`.

Consolidation counts: **88** literal hexes in `styles.css` → tokens, plus **32**
rgba triples; **150** chart hexes in `app.js` → `PRAVAHA.*`, plus 19 rgba; 13 in
`kronos_ui.js`; `viz.js` TOKEN/PALETTE rewritten to read CSS variables.

Colour distribution follows the guide: dark neutral surfaces dominate; emerald is
reserved for primary actions, active nav and selection; cyan is the secondary
series/focus cue; amber and coral are used **only** for caution and risk. Currency
and price cells keep explicit `+`/`−` signs and arrows, so colour is never the
sole carrier of financial meaning.

**Fonts:** no external font dependency was added — the app must work fully
offline. The preferred families are named first in each stack and degrade to
system fonts if not installed locally. This is a deliberate trade-off
(*documented limitation*, not an oversight).

## E. Files modified

```
web/static/styles.css              token system, brand layer, colour consolidation, media query
web/static/index.html              title/meta/favicon, brand lockup, footer, cache-busters
web/static/app.js                  PRAVAHA palette object, chart colour consolidation, brand copy
web/static/viz.js                  CSS-variable-driven TOKEN + new PALETTE, gauge zones
web/static/kronos_ui.js            colour consolidation
web/static/indicator_info.js       one user-facing copy string
web/static/dashboard.html          legacy page → branded redirect stub
web/static/market_dashboard.html   legacy page → branded redirect stub
web/static/research.html           legacy page → branded redirect stub
web/static/brand/*.png             six new brand assets
tests/test_api.py                  brand assertion updated (see §G)
PRAVAHA_REBRAND_REPORT.md          this report (new)
MASTER_MISSION_CHECKLIST.md        §10 appended (new section)
docs/screenshots/pravaha-before/   11 baseline screenshots (new)
docs/screenshots/pravaha-after/    13 post-change screenshots (new)
```

Retained on purpose (internal contracts, **not** product branding): the
`megatool-api-base` meta tag, `window.MEGATOOL_API_BASE`, the
`megatool_friend_token` storage key, `megatool.*` module paths quoted as data
provenance, the real `megatool walk-forward` / `megatool pdf import` CLI
commands, and the Python package name.

## F. Before-and-after screenshots

- `docs/screenshots/pravaha-before/` — 10 views captured before any change
  (overview, charts, screener, backtest, kimi, sastoshare, fundamentals,
  portfolio, data, marketintel).
- `docs/screenshots/pravaha-after/` — 15 captures: the same 10 views plus
  breadth, forecaster, `charts-loaded.png` (a real NABIL daily chart with the new
  palette), `narrow-overview.png` (760 px responsive strip) and
  `legacy-redirect-stub.png` (the rebranded redirect page for the retired static
  dashboards).

## G. Tests executed and actual results

All results below are the actual outputs of the commands shown — nothing was
inferred or assumed.

| # | Command | Result |
|---|---|---|
| G-1 | `MEGATOOL_DATA_DIR=… .venv/bin/python -m pytest -q -p no:warnings --junitxml=…` | **2,970 collected / 0 failed / 0 errors / 14 skipped / exit 0** |
| G-2 | `MEGATOOL_BROWSER_TESTS=1 … pytest tests/test_browser_objects_manager.py tests/test_browser_viz_toolinfo.py -q` | **14 passed** (14 dots, exit 0) |
| G-3 | `node --check web/static/app.js`, `viz.js`, `kronos_ui.js`, `indicator_info.js` | all **OK** |
| G-4 | `ruff check` + `ruff format --check` on `tests/test_api.py` | clean |
| G-5 | `ruff check megatool/api.py` | 18 findings, **all pre-existing** |
| G-6 | Nav sweep: every `[data-view]` destination clicked in a real browser, JS errors captured | **40/40 visited, 0 JS errors, 0 `showView` failures** |
| G-7 | Browser console over all captured screenshots | **0 errors, 0 warnings** |

G-5 detail: the same 18 findings exist in the committed version of
`megatool/api.py`. `ruff check` on `git show HEAD:megatool/api.py` reports
`All checks passed!` at 1,426 lines; the current file is 5,771 lines, with every
one of the 18 findings sitting in the market-intelligence route blocks added by
earlier work (imports at line 10, and routes near lines 1335–1505, 2402–2502,
2612, 2659, 4209). **None** is in the region this task edited (the FastAPI
`title`/`description` at lines 847–856). They were left alone: reformatting a
thousand lines of backend routing during a branding task would be unrelated churn.

One assertion was deliberately invalidated and updated:
`tests/test_api.py::test_ui_is_served` asserted `"Mega Tool" in r.text` — that
pinned the old product name. It now asserts:

```python
assert "PRAVAHA" in r.text
assert "Mega Tool" not in r.text
```

The suite still passes 2,970/0/0. This is recorded here rather than silently
edited: changing an assertion to match an intentional, disclosed product change
is not the same as weakening a test to hide a failure. The assertion continues to
verify the same invariant (the app shell is served, attribution present); only
the product name it pins has moved.


## H. Functional regressions discovered

- **Responsive navigation.** The first brand-layer media query overrode the app's
  existing ≤900 px behaviour (a single horizontally scrollable nav strip) and
  wrapped the nav into many rows, pushing the brand into the middle of the list.
  Reverted to a re-skin-only media query; the original strip behaviour is intact
  (verified: `flex-direction: row`, `overflow-x: auto`, 66 px tall).
- **Chart colours were outside the token system.** The charting engine and the
  SVG module held their own colour literals, so a stylesheet-only rebrand would
  have left the most prominent surface unstyled. Fixed by the palette object and
  the CSS-variable read in `viz.js`.
- **Obsolete styling.** `.logo` / `.side-brand .logo` (the old "MT" chip) became
  dead after the lockup swap and were removed after grep-verifying no HTML/JS
  reference them.

## I. Remaining visual / functional issues

- Fonts degrade to system families unless Space Grotesk / Inter / JetBrains Mono
  are installed (offline-first decision).
- The supplied logo has no transparency; the mark is presented inside a rounded
  container rather than keyed out.
- `app.js` still contains colour literals inside a handful of dynamically
  generated strings that were already tokenised at the source; no new ones were
  introduced.
- Legacy `/dashboard.html`, `/market_dashboard.html`, `/research.html` now
  redirect into the SPA. Their original static content was unverifiable and is
  intentionally not reproduced.

## J. Items NOT-TESTED or BLOCKED

- **Login / authentication / About / loading screens** — do not exist in this
  application (single-page, no auth). Marked N/A.
- **Live-data status chips** — the `LIVE` state cannot be exercised because there
  is no live NEPSE feed in this environment; every surface correctly reports
  `DELAYED` / `historical`. The `LIVE` chip style is defined but unproven.
- **`prefers-reduced-motion`** — CSS verified present; not exercised with a real
  OS-level reduced-motion setting.

## K. Production port 8710

**Not modified.** No process on `:8710` was started, stopped or contacted. All
work was done against the development server on `:10000`.

## L. Commit / push / deploy

**None.** No `git add`, `commit`, `push`, tag, release or deployment was
performed. No destructive git operation was run. The working tree remains
uncommitted, exactly as found.

## M. How to view the updated development application

```bash
cd "/Users/ashim/Downloads/AI trading NEPSE"
lsof -ti tcp:10000 -sTCP:LISTEN | xargs -r kill; sleep 2
MEGATOOL_DATA_DIR="$PWD/data/dev/release" \
  nohup .venv/bin/python -m megatool.cli serve --host 127.0.0.1 --port 10000 \
  > "$TMPDIR/dev_server.log" 2>&1 &
open http://127.0.0.1:10000/
```

Static-only edits need no server restart; hard-reload once (the cache-busters for
`styles.css`, `app.js`, `viz.js`, `kronos_ui.js` and `indicator_info.js` were
bumped). Python changes require the restart above. Production (`:8710`) is
untouched.
