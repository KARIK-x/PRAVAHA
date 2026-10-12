"""Benchmark scorer: compares OCR methods against ground truth for 5 handwritten pages.

Priority 2 of MEGA_TOOL_RESEARCH_REPORT.md.

Metrics per page and method:
  - number_exact : target number found verbatim (commas/spaces removed)
  - number_numeric: target's digit sequence found (punctuation-insensitive)
  - symbol_exact : stock symbol found (case-insensitive)
Recall only: ground truth is a subset of page content, so this measures
"how much of the known-good financial data each method recovers".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "written_pdf" / "benchmark"
OCR = ROOT / "data" / "written_pdf" / "raw_ocr"


def norm(s: str) -> str:
    return re.sub(r"[,\s]", "", s).upper()


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s)


def targets_for(page: str, gt: dict) -> tuple[list[str], list[str]]:
    """Return (number targets, symbol targets) for a page."""
    spec = gt[f"p{page}"]
    nums: list[str] = []
    for key in ("prices", "totals", "other_values", "line_prices"):
        for v in spec.get(key, []):
            nums.append(str(v))
    for st in spec.get("settlements", []):
        nums.extend([str(st["buy"]), str(st["sell"]), str(st["net"])])
    syms = [s.upper() for s in spec.get("symbols", [])]
    return nums, syms


VISION = ROOT / "data" / "written_pdf" / "vision_ocr"


def read_method(page: str, method: str) -> str:
    if method == "tesseract":
        p = OCR / f"page_{page}.txt"
    elif method == "apple_vision":
        p = BENCH / f"vision_p{page}.txt"
    elif method == "apple_vision_rot":
        # Batch pass over all 52 pages with orientation detection
        # (scripts/vision_ocr_batch.swift). Same engine, best of 4 rotations.
        p = VISION / f"page_{page}.txt"
        if not p.exists():
            return ""
        # Skip the provenance header, keep only recognised lines.
        body = p.read_text(errors="replace")
        return body.split("\n---\n", 1)[-1]
    else:
        raise ValueError(method)
    if not p.exists():
        return ""
    return p.read_text(errors="replace")


def score(page: str, gt: dict, method: str) -> dict:
    nums, syms = targets_for(page, gt)
    out = read_method(page, method)
    n_out, d_out = norm(out), digits(out)

    n_exact = sum(1 for t in nums if norm(t) in n_out)
    n_num = sum(1 for t in nums if digits(t) in d_out)
    s_exact = sum(1 for t in syms if t in n_out)

    return {
        "page": page,
        "method": method,
        "n_total": len(nums),
        "n_exact": n_exact,
        "n_numeric": n_num,
        "s_total": len(syms),
        "s_exact": s_exact,
        "bytes": len(out.encode()),
    }


def main() -> int:
    gt = json.loads((BENCH / "ground_truth.json").read_text())
    pages = ["02", "09", "11", "18", "21"]
    methods = ["tesseract", "apple_vision"]
    # Only score the rotation-aware pass once it has actually been run.
    if any((VISION / f"page_{p}.txt").exists() for p in pages):
        methods.append("apple_vision_rot")

    rows = [score(p, gt, m) for p in pages for m in methods]

    print(
        f"{'page':<6}{'method':<16}{'numbers':>12}{'exact':>9}{'numeric':>10}{'symbols':>12}{'bytes':>9}"
    )
    print("-" * 74)
    for r in rows:
        print(
            f"p{r['page']:<5}{r['method']:<16}"
            f"{str(r['n_exact']) + '/' + str(r['n_total']):>12}"
            f"{r['n_exact'] / r['n_total'] * 100:>8.0f}%"
            f"{r['n_numeric'] / r['n_total'] * 100:>9.0f}%"
            f"{str(r['s_exact']) + '/' + str(r['s_total']):>12}"
            f"{r['bytes']:>9}"
        )

    print()
    print("TOTALS")
    for m in methods:
        rs = [r for r in rows if r["method"] == m]
        nt = sum(r["n_total"] for r in rs)
        ne = sum(r["n_exact"] for r in rs)
        nn = sum(r["n_numeric"] for r in rs)
        st = sum(r["s_total"] for r in rs)
        se = sum(r["s_exact"] for r in rs)
        print(
            f"  {m:<16} numbers exact {ne}/{nt} ({ne / nt * 100:.1f}%) | "
            f"numeric {nn}/{nt} ({nn / nt * 100:.1f}%) | "
            f"symbols {se}/{st} ({se / st * 100:.1f}%)"
        )

    # Persist for the report.
    (BENCH / "results.json").write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {BENCH / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
