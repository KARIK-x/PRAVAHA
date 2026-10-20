import { describe, it, expect } from "vitest";
import {
  nptParts,
  isTradingDay,
  isMarketWindow,
  parseSourceTime,
  newestIso,
  validateDataset,
  normaliseHistory,
  freshnessLabel,
  classifyRun,
  compactSnapshot,
  mergeMetadata,
  sourceUpdatedAt,
  YONEPSE_BASE,
  DATASETS,
} from "../src/yonepse.js";

describe("Nepal clock (UTC+05:45)", () => {
  it("converts a UTC instant to NPT wall clock", () => {
    // 2026-10-19T05:15:00Z === 2026-10-19 11:00 NPT (market open)
    const p = nptParts(new Date("2026-10-19T05:15:00Z"));
    expect(p.iso).toBe("2026-10-19T11:00:00+05:45");
    expect(p.hour).toBe(11);
    expect(p.weekday).toBe(1); // Monday
  });

  it("knows trading days and the market window", () => {
    expect(isTradingDay(new Date("2026-10-19T05:15:00Z"))).toBe(true); // Mon
    expect(isTradingDay(new Date("2026-10-18T05:15:00Z"))).toBe(false); // Sun
    expect(isMarketWindow(new Date("2026-10-19T05:15:00Z"))).toBe(true); // 11:00 NPT
    expect(isMarketWindow(new Date("2026-10-19T04:00:00Z"))).toBe(false); // 09:45 NPT
    expect(isMarketWindow(new Date("2026-10-19T10:30:00Z"))).toBe(false); // 16:15 NPT
  });
});

describe("source timestamps", () => {
  it("parses a naive NPT stamp as Nepal time (not UTC)", () => {
    const d = parseSourceTime("2026-10-19T10:17:10.720403");
    expect(d.toISOString()).toBe("2026-10-19T04:32:10.720Z");
  });
  it("honours an explicit zone", () => {
    expect(parseSourceTime("2026-05-18T19:23:40+05:45").toISOString()).toBe(
      "2026-05-18T13:38:40.000Z"
    );
    expect(parseSourceTime("2026-05-18T13:38:40Z").toISOString()).toBe(
      "2026-05-18T13:38:40.000Z"
    );
  });
  it("returns null for junk rather than inventing a time", () => {
    expect(parseSourceTime("")).toBeNull();
    expect(parseSourceTime(null)).toBeNull();
    expect(parseSourceTime("not-a-date")).toBeNull();
  });
  it("picks the newest of several stamps", () => {
    expect(newestIso(["2026-10-16T10:00:00", "2026-10-19T10:17:10"])).toBe(
      "2026-10-19T04:32:10.000Z"
    );
  });
});

describe("validateDataset", () => {
  it("accepts the documented shapes", () => {
    expect(validateDataset("data/market/indices.json", [{ index: "NEPSE" }], "array")).toBeNull();
    expect(
      validateDataset("data/market/status.json", { is_open: false, last_checked: "x" }, "object")
    ).toBeNull();
  });
  it("rejects a wrong shape", () => {
    expect(validateDataset("data/market/indices.json", { a: 1 }, "array")).toMatch(/expected array/);
    expect(validateDataset("data/market/status.json", [1], "object")).toMatch(/expected object/);
  });
  it("rejects an empty payload", () => {
    expect(validateDataset("data/market/indices.json", [], "array")).toMatch(/empty array/);
    expect(validateDataset("data/market/status.json", {}, "object")).toMatch(/empty object/);
  });
  it("requires a boolean is_open and a last_checked on status", () => {
    expect(validateDataset("data/market/status.json", { is_open: "yes" }, "object")).toMatch(
      /is_open is not a boolean/
    );
    expect(validateDataset("data/market/status.json", { is_open: true }, "object")).toMatch(
      /last_checked missing/
    );
  });
});

describe("history shape", () => {
  it("accepts the documented {columns,rows} form", () => {
    const rows = normaliseHistory({
      columns: ["businessDate", "totalTurnover"],
      rows: [["2026-10-16", 4880089108.16]],
    });
    expect(rows).toEqual([{ businessDate: "2026-10-16", totalTurnover: 4880089108.16 }]);
  });
  it("accepts a list of row objects too", () => {
    expect(normaliseHistory([{ businessDate: "2026-10-16" }])).toEqual([
      { businessDate: "2026-10-16" },
    ]);
  });
  it("returns [] for anything else", () => {
    expect(normaliseHistory(null)).toEqual([]);
    expect(normaliseHistory("nope")).toEqual([]);
  });
});

describe("freshness (mirrors megatool/live.py)", () => {
  it("labels a sub-30s observation live", () => {
    expect(freshnessLabel(10, true)).toBe("live");
  });
  it("labels a closed market's last close as last-close, NOT stale", () => {
    expect(freshnessLabel(6 * 3600, false)).toBe("last-close");
    expect(freshnessLabel(3 * 24 * 3600 - 1, false)).toBe("last-close");
  });
  it("labels a source beyond its cadence as stale", () => {
    expect(freshnessLabel(4 * 24 * 3600, true)).toBe("stale");
  });
  it("labels a very old observation historical", () => {
    expect(freshnessLabel(9 * 24 * 3600, false)).toBe("historical");
  });
  it("never claims freshness without a timestamp", () => {
    expect(freshnessLabel(null, true)).toBe("unknown");
    expect(freshnessLabel(NaN, true)).toBe("unknown");
  });
});

describe("classifyRun (dedupe / holidays)", () => {
  it("first run is a change", () => {
    expect(classifyRun(null, "2026-10-16T10:00:00.000Z", false)).toEqual({
      changed: true,
      reason: "first-run",
    });
  });
  it("a new source stamp is a change", () => {
    expect(
      classifyRun({ source_updated_at: "A" }, "B", true)
    ).toEqual({ changed: true, reason: "source-advanced" });
  });
  it("an unchanged payload while open is 'unchanged'", () => {
    expect(classifyRun({ source_updated_at: "A" }, "A", true)).toEqual({
      changed: false,
      reason: "unchanged",
    });
  });
  it("an unchanged payload while closed is 'closed-unchanged' (not a failure)", () => {
    expect(classifyRun({ source_updated_at: "A" }, "A", false)).toEqual({
      changed: false,
      reason: "closed-unchanged",
    });
  });
});

describe("compactSnapshot", () => {
  const datasets = {
    status: { is_open: false, last_checked: "2026-10-19T10:17:10" },
    indices: [{ index: "NEPSE", close: 2634.17, perChange: 0.31, generatedTime: "2026-10-19T10:00:00" }],
    summary: [{ detail: "Total Turnover Rs:", value: 4880089108.16 }],
    history: { columns: ["businessDate", "totalTurnover"], rows: [["2026-10-16", 1], ["2026-10-17", 2]] },
    ltpManifest: { latestDate: "2026-10-16", latestStatus: "final" },
    quotes: [
      { symbol: "NABIL", ltp: 547, last_updated: "2026-10-16T14:00:00" },
      { symbol: "ADBL", ltp: null, last_updated: "2026-10-16T14:00:00" },
    ],
  };
  const snap = compactSnapshot(datasets, {
    retrieved_at: "2026-10-19T16:00:00.000Z",
    source_updated_at: "2026-10-19T04:32:10.000Z",
  });

  it("separates retrieval time from the source update time", () => {
    expect(snap.retrieved_at).toBe("2026-10-19T16:00:00.000Z");
    expect(snap.source_updated_at).toBe("2026-10-19T04:32:10.000Z");
  });
  it("carries status, counts and the index/summary rows", () => {
    expect(snap.is_open).toBe(false);
    expect(snap.quote_count).toBe(2);
    expect(snap.missing_price).toBe(1);
    expect(snap.indices[0].index).toBe("NEPSE");
    expect(snap.history_latest.businessDate).toBe("2026-10-17");
  });
  it("NEVER contains OHLCV candle fields", () => {
    const json = JSON.stringify(snap);
    for (const banned of ['"open"', '"high"', '"low"', '"candle"', '"ohlc"']) {
      expect(json.includes(banned)).toBe(false);
    }
  });
  it("is small enough for KV (well under the 25 MB value limit)", () => {
    expect(JSON.stringify(snap).length).toBeLessThan(20_000);
  });
});

describe("mergeMetadata", () => {
  it("counts successes and clears the failure reason", () => {
    const m = mergeMetadata({ runs: 4, last_failure_reason: "boom", consecutive_failures: 2 }, {
      ok: true,
      retrieved_at: "T",
      reason: "unchanged",
    });
    expect(m.runs).toBe(5);
    expect(m.last_failure_reason).toBeNull();
    expect(m.consecutive_failures).toBe(0);
    expect(m.last_success_at).toBe("T");
  });
  it("keeps the last success when a run fails", () => {
    const m = mergeMetadata({ runs: 1, last_success_at: "S" }, {
      ok: false,
      retrieved_at: "T",
      reason: "critical datasets failed: status",
    });
    expect(m.last_success_at).toBe("S");
    expect(m.last_failure_at).toBe("T");
    expect(m.consecutive_failures).toBe(1);
  });
});

describe("sourceUpdatedAt", () => {
  it("picks the newest across status/indices/quotes", () => {
    const at = sourceUpdatedAt({
      status: { last_checked: "2026-10-19T10:17:10" },
      indices: [{ generatedTime: "2026-10-19T10:00:00" }],
      quotes: [{ last_updated: "2026-10-16T14:00:00" }],
    });
    expect(at).toBe("2026-10-19T04:32:10.000Z");
  });
});

describe("dataset contract", () => {
  it("uses only documented public endpoints on the documented base", () => {
    expect(YONEPSE_BASE).toBe("https://shubhamnpk.github.io/yonepse");
    for (const d of DATASETS) {
      expect(d.path.startsWith("data/")).toBe(true);
      expect(d.path.includes("..")).toBe(false);
    }
  });
});
