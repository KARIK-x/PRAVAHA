# KIMI — Checkpoint

## State
- KIMI is a top-level sidebar section with 13 tabs, all real.
- Catalogues tab exposes 229 tools (124 scanners / 77 algorithms / 32
  fundamental tools) with search, category filter, ⓘ panel and Run.
- Store-backed analysis works through the API via the store-provider hook.
- All 13 KIMI tabs and all 34 top-level views render clean (0 "undefined",
  0 console errors).

## Tests
- `tests/test_catalog.py` — 52 passed.
- Full suite — 2,791 passed / 0 failed / 8 skipped, exit 0.
- Browser walk — clean.

## Open
- Full click-through of all 229 catalogue entries (sampled per family).
- Blocked capabilities (floorsheet, events, DPS, ownership, scheduler, PIT,
  revisions, live feed) remain BLOCKED and are labelled as such.
