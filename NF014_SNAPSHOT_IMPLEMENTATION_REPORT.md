# NF-014 — Calculation Snapshots & Reproducibility

**Module:** `megatool/snapshots.py`
**API:** `POST/GET /api/snapshots`, `GET /api/snapshots/{id}`, `POST /api/snapshots/{id}/rerun`, `POST /api/snapshots/compare`, `POST /api/snapshots/capture`
**UI:** KIMI → **Snapshots** tab
**Table:** `calculation_snapshots` (schema v10)
**Tests:** `tests/test_snapshots.py` (15)
**Date:** 2026-10-19

---

## 1. What a snapshot is

A snapshot freezes *how a number was produced* so it can be re-checked later: the
feature, the input fingerprint, the parameter set, the data cutoff, the source ids, the
methodology (description + formula), and the result. It is written to
`calculation_snapshots` and can be reopened, compared and re-run.

The engine's job is to **never claim reproducibility it cannot support**.

---

## 2. Reproducibility classification

The **module** decides the class; a caller cannot assert `fully_reproducible`.

| Class | When it is assigned |
|---|---|
| `fully_reproducible` | inputs are a pure function of stored data + declared params + a known data cutoff (e.g. `technical_rating`, `monte_carlo` with a seed) |
| `partially_reproducible` | an input is recoverable but not pinned (e.g. a live-ish or time-dependent input) |
| `unrecoverable` | an input cannot be recovered, so a later re-run would not mean the same thing |

A snapshot is only *labelled* reproducible when its inputs, versions and methodology are
actually recoverable.

---

## 3. Observed behaviour (release data)

Four snapshots recorded during verification:

```
snap-20261019T022925-ddeb536a  technical_rating  fully_reproducible
snap-20261019T020703-253ce24c  monte_carlo        fully_reproducible
snap-20261019T020642-afe43d59  monte_carlo        fully_reproducible
snap-20261019T020642-91fefa1e  technical_rating  fully_reproducible
```

A snapshot's stored fields (abridged):

```json
{
  "id": "snap-20261019T022925-ddeb536a",
  "feature": "technical_rating",
  "created_at": "2026-10-19T02:29:25+00:00",
  "data_cutoff": "2026-10-15",
  "universe": "ACLBSL",
  "date_range": "2020-07-29..2026-10-15",
  "source_ids": ["github.com/Aabishkar2/nepse-data"],
  "input_hash": "8c777697…c11d71b",
  "params": {"symbol": "ACLBSL"},
  "methodology": {"description": "…", "formula": "…"}
}
```

**Rerun determinism:** `POST /api/snapshots/snap-20261019T022925-ddeb536a/rerun`
returned `{"reproduced": true, "diff": null}`.

---

## 4. Secret hygiene

* Parameters are scrubbed of secret-like keys using **whole-token matching** (so an
  innocuous key such as `monkey_rank` is preserved, while a real key/token is removed).
* Scrubbing happens **before** the engine runs, so a secret cannot reach the result,
  the hash, or the stored row.
* Covered by a dedicated test that plants a secret-like parameter and asserts it never
  appears in the persisted snapshot.

---

## 5. Capture, create, compare, rerun

| Operation | Endpoint | Behaviour |
|---|---|---|
| Capture a live calculation | `POST /api/snapshots/capture` | runs the feature, records inputs+result, classifies reproducibility |
| Create explicitly | `POST /api/snapshots` | creates from supplied metadata/result |
| Get | `GET /api/snapshots/{id}` | returns the full snapshot (404 if absent) |
| List | `GET /api/snapshots` | newest first |
| Compare | `POST /api/snapshots/compare` | parameter / result / version diffs |
| Rerun | `POST /api/snapshots/{id}/rerun` | re-executes and reports `reproduced` + diff |
| List | `GET /api/snapshots` | returned 4 snapshots during verification |

A rerun that cannot reproduce its inputs is **refused** (a stated error) rather than
reported as an equal result.

---

## 6. Verification

* **Unit:** `tests/test_snapshots.py` — 15 tests: capture metadata, partial/unrecoverable
  classification, pure-calculation seed, secret scrubbing, deterministic
  input/results hash, get/list, deterministic rerun, rerun refusal, compare param/result/
  version diffs, unique ids, explicit create. **PASS.**
* **API:** `tests/test_phase_api.py` — snapshot routes incl. 404. **PASS.**
* **Browser (dev :10000):** Snapshots tab → **Capture** → "Captured snap-… —
  reproducibility: fully_reproducible", list populated. **PASS.**
* **Standalone:** capture/rerun/compare exercised against `data/dev/qa`.

---

## 7. Limitations

* A snapshot of a live/streaming input is `partially_reproducible` at best and says so.
* `unadjusted` prices are recorded as such: a snapshot taken before a corporate action
  would not reproduce after one, and the adjustment status is part of the record.
* Snapshots record methodology text; they do not re-prove the formula. The hash and the
  recorded inputs are what make a re-check meaningful.
* No secret is ever written; if a caller passes one, it is scrubbed and the snapshot is
  still valid for the non-secret inputs.
