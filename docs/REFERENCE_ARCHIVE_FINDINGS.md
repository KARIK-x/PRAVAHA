# Reference archive (Part A) — findings

## The archive is **not present**

The task states the photographs are in `/Users/ashim/Downloads/Archive.zip`
(20 handwritten JPGs, `IMG_0597.JPG` … `IMG_0616.JPG`).

**That file does not exist.** It was searched for directly and by filename:

* `ls /Users/ashim/Downloads/Archive.zip` → `No such file or directory`
* `find /Users/ashim -maxdepth 6 -iname "Archive*.zip"` → only the unrelated
  `stitch_locus_archive_machine/` directory
* `find /Users/ashim -maxdepth 8 -iname "IMG_06*"` → only `IMG_0635.PNG` and
  `IMG_0636.PNG`, which are unrelated to the stated range
* No `.zip` files at all under `~/Downloads`

`PHOTOS/` inside the project holds UI screenshots (`Screenshot 2026-10-16 …`,
2.0–2.7 MB each), **not** handwritten notebook photographs.

**Consequence:** no photograph in the stated range was read, and no handwriting
was transcribed. Any claim about the content of `IMG_0597`–`IMG_0616` would be
invented, so none is made.

## What *is* available instead

The same notebook has already been digitised in earlier sessions, from
`WRITTENdata.pdf`. Those artefacts are present:

| Path | What it is |
|---|---|
| `WRITTENdata.pdf` | The notebook itself (7.3 MB, 52 pages) |
| `digitized_trading_ledger_and_notes.md` | NotebookLM narrative digitisation |
| `trading_ledger_master_data.xlsx` | NotebookLM structured trades register + EPS sheets |
| `Written_Data_All_52_Pages_Digitized.xlsx` | ChatGPT page-by-page workbook + preliminary OCR |
| `Written_Data_Full_Transcription.xlsx` | Third transcription |
| `megatool/written_reference.py` | Loader that tags all three as **`secondary_digitization`** / **`unverified`** |

Four existing docs describe them: `docs/WRITTEN_DATA_{DICTIONARY,IMPORT_GUIDE,PDF_AUDIT,VALIDATION_REPORT}.md`.

**These are not ground truth.** `megatool.written_reference` is explicit that a
"Market Price" in them is what the notebook wrote on an unknown date, *not* a
current NEPSE price, and that feeding it to anything implying liveness "would be
a lie".

## Recoverable structure (from the documented digitisations, unverified)

Only what the existing docs report — treat as leads, not facts:

* **Trade registers** with an explicit settlement label per trade
* **Banking / microfinance and hydropower EPS sheets**
* **Sector valuation tables**, **indicator scoreboards**, **strategy rules**,
  **watchlists**
* **Broker settlement** records whose PDF page numbers are known

## What this means for BABA

The BABA data model is therefore built from **what the existing loaders and
database already support** (`megatool/journal.py`, `megatool/portfolio.py`,
`megatool/fundamentals.py`, `megatool/sectors.py`), not from a fresh reading of
the photographs.

If the intended 20 photographs are supplied, the correct next step is a
review-and-confirm import: retain the original image reference, keep the raw
extracted text, record field-level confidence, and require human confirmation
before anything becomes a verified transaction. `megatool.written_reference`
already enforces the "never silently promote uncertain handwriting" rule and
should be reused rather than replaced.
