"""Run Apple Vision OCR across the handwritten notebook pages.

Reads the already-rendered page images in ``data/written_pdf/raw_pages`` and
writes one provenance-headed text file per page into
``data/written_pdf/vision_ocr``. Output is deliberately *not* a transcription:
every file is stamped ``status: OCR_ONLY`` so machine text can never be
mistaken for a verified reading.

Design constraints:
  - Idempotent and resumable: an existing page file is skipped unless
    ``--force`` is given, so a failed batch never loses earlier work.
  - Bounded batches: each batch is one short-lived ``swift`` process, so a
    crash costs at most one batch.
  - Local only: no network, no model download, no system change.

Usage:
    python scripts/run_vision_ocr.py               # all missing pages
    python scripts/run_vision_ocr.py --pages 18-33 # settlement pages first
    python scripts/run_vision_ocr.py --force       # redo everything
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "data" / "written_pdf" / "raw_pages"
OUT = ROOT / "data" / "written_pdf" / "vision_ocr"
SWIFT = ROOT / "scripts" / "vision_ocr_batch.swift"
STATUS = ROOT / "data" / "written_pdf" / "vision_ocr_status.json"

ENGINE = "apple-vision VNRecognizeTextRequest .accurate en-US"


def parse_pages(spec: str) -> list[int]:
    """Parse ``"18-33"`` / ``"1,5,21"`` / ``"1-5,18-33"`` into page numbers."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def header(meta: dict) -> str:
    lines = [f"# {k}: {v}" for k, v in meta.items()]
    return "\n".join(lines) + "\n---\n"


def run_batch(paths: list[Path]) -> list[dict]:
    proc = subprocess.run(
        ["swift", str(SWIFT), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"swift exited {proc.returncode}: {proc.stderr[:500]}")
    results = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        results.append(json.loads(line))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="", help='e.g. "1-52" or "18-33"')
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    wanted = parse_pages(args.pages) if args.pages else list(range(1, 53))
    wanted = [p for p in wanted if 1 <= p <= 52]
    if not wanted:
        print("no pages selected")
        return 2

    todo = []
    for p in wanted:
        img = IMAGES / f"page_{p:02d}.png"
        dst = OUT / f"page_{p:02d}.txt"
        if not img.exists():
            print(f"  MISSING IMAGE page {p}: {img}")
            continue
        if dst.exists() and not args.force:
            continue
        todo.append((p, img))

    print(f"selected {len(wanted)} pages, {len(todo)} to run")
    if not todo:
        print("nothing to do (idempotent skip)")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    done: list[dict] = []
    failed: list[int] = []
    for i in range(0, len(todo), args.batch):
        chunk = todo[i : i + args.batch]
        pages = [p for p, _ in chunk]
        print(f"  batch {i // args.batch + 1}: pages {pages} ...", flush=True)
        try:
            results = run_batch([img for _, img in chunk])
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"    FAILED: {exc}")
            failed.extend(pages)
            continue
        by_page = {int(re.search(r"page_(\d+)", r["path"]).group(1)): r for r in results}
        for p, _ in chunk:
            r = by_page.get(p)
            if r is None:
                failed.append(p)
                continue
            if r.get("error"):
                failed.append(p)
                print(f"    page {p}: {r['error']}")
                continue
            cand = " ".join(f"{c['orientation']}={c['score']}" for c in r["candidates"])
            text = "\n".join(item["text"] for item in r["lines"])
            meta = {
                "page": f"{p:02d}",
                "source": str((IMAGES / f"page_{p:02d}.png").relative_to(ROOT)),
                "engine": ENGINE,
                "orientation": r["best_orientation"],
                "score": r["best_score"],
                "lines": len(r["lines"]),
                "mean_confidence": round(
                    sum(item["confidence"] for item in r["lines"]) / max(len(r["lines"]), 1),
                    3,
                ),
                "candidates": cand,
                "duration_s": round(r["duration_s"], 2),
                "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "status": "OCR_ONLY",
                "note": (
                    "Machine OCR of handwritten page. NOT a verified "
                    "transcription; do not use for accounting or fundamentals."
                ),
            }
            (OUT / f"page_{p:02d}.txt").write_text(header(meta) + text + "\n", encoding="utf-8")
            done.append(
                {
                    "page": p,
                    **{k: meta[k] for k in ("orientation", "score", "lines", "mean_confidence")},
                }
            )
            print(
                f"    page {p}: {meta['orientation']:<5} lines={meta['lines']:<4} chars={len(text)}"
            )

    STATUS.write_text(
        json.dumps(
            {
                "engine": ENGINE,
                "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "completed": done,
                "failed": failed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\ncompleted {len(done)}, failed {len(failed)}")
    if failed:
        print(f"failed pages: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
