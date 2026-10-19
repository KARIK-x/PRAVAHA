"""Command-line interface.

    python -m market_intelligence.cli.main initdb --db data/mi.db
    python -m market_intelligence.cli.main load-registry --db ... --registry data/registry/source_registry.json
    python -m market_intelligence.cli.main collect --db ... [--source-id X] [--dry-run] [--max-sources N]
    python -m market_intelligence.cli.main evaluate --dataset data/evaluation/sentiment_eval.json
    python -m market_intelligence.cli.main export-kronos-features --db ... --entity-id ... --ticker NABIL
    python -m market_intelligence.cli.main serve --db ... [--port 8080]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _connect(args):
    from ..database.db import connect, run_migrations
    conn = connect(args.db)
    run_migrations(conn, PROJECT_ROOT / "migrations")
    return conn


def cmd_initdb(args):
    conn = _connect(args)
    n = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    print(f"database ready at {args.db} ({n} migration(s) applied)")


def cmd_load_registry(args):
    from ..database.db import upsert_source
    conn = _connect(args)
    data = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    n = 0
    for rec in data["sources"]:
        upsert_source(conn, rec)
        n += 1
    conn.commit()
    print(f"loaded {n} sources from {args.registry}")


def cmd_collect(args):
    from ..database.db import insert_event, link_event_article, new_id
    from ..entities.registry import EntityRegistry
    from ..event_detection.classifier import EventClassifier
    from ..ingestion.common.http import HttpFetcher
    from ..ingestion.pipeline import Pipeline
    from ..ingestion.rss.collector import RSSAdapter
    from ..normalization.timestamps import now_utc_iso
    from ..sentiment.lexicon import LexiconSentimentModel

    conn = _connect(args)
    ent_path = PROJECT_ROOT / "data" / "registry" / "entity_aliases.json"
    ereg = EntityRegistry.load(ent_path) if ent_path.exists() else None
    pipe = Pipeline(conn, entity_registry=ereg,
                    sentiment_model=LexiconSentimentModel(),
                    event_classifier=EventClassifier())
    fetcher = HttpFetcher(dry_run=args.dry_run,
                          collection_enabled=not args.disable_collection)
    q = "SELECT * FROM sources WHERE automated_access_status IN ('VERIFIED','APPROVED') AND rss_url IS NOT NULL"
    params: list = []
    if args.source_id:
        q += " AND source_id = ?"
        params.append(args.source_id)
    q += " LIMIT ?"
    params.append(args.max_sources)
    sources = conn.execute(q, params).fetchall()
    total_new = total_dup = total_fail = 0
    for s in sources:
        adapter = RSSAdapter(dict(s), fetcher)
        report = adapter.collect(max_items=args.max_items)
        job_id = new_id("job")
        if not report.ok:
            conn.execute(
                """INSERT INTO collection_jobs (job_id, job_type, source_id, started_at,
                   finished_at, status, error) VALUES (?,?,?,?,?,?,?)""",
                (job_id, "rss", s["source_id"], now_utc_iso(), now_utc_iso(),
                 "failed", report.error))
            conn.commit()
            total_fail += 1
            print(f"FAIL {s['source_id']}: {report.error}")
            continue
        new = dup = 0
        for raw in report.items:
            out = pipe.process(s["source_id"], raw)
            new += out["status"] == "stored"
            dup += out["status"] == "duplicate"
        conn.execute(
            """INSERT INTO collection_jobs (job_id, job_type, source_id, started_at,
               finished_at, status, records_fetched, records_new, records_duplicate)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (job_id, "rss", s["source_id"], now_utc_iso(), now_utc_iso(),
             "dry_run" if args.dry_run else "success",
             len(report.items), new, dup))
        conn.execute("UPDATE sources SET last_successful_fetch_at=? WHERE source_id=?",
                     (now_utc_iso(), s["source_id"]))
        conn.commit()
        total_new += new; total_dup += dup
        print(f"OK {s['source_id']}: {len(report.items)} fetched, {new} new, {dup} dup")
    print(f"done: {len(sources)} sources, {total_new} new, {total_dup} duplicates, {total_fail} failed")


def cmd_evaluate(args):
    from ..evaluation.metrics import precision_recall_f1
    from ..language.detect import detect_language
    from ..sentiment.lexicon import LexiconSentimentModel

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    model = LexiconSentimentModel()
    y_true, y_pred = [], []
    per_lang: dict[str, dict] = {}
    for ex in data["examples"]:
        lang = detect_language(ex["text"])
        pred = model.predict(ex["text"], language=lang.language)
        pred.validate()
        y_true.append(ex["label"])
        y_pred.append(pred.general_sentiment)
        bucket = per_lang.setdefault(lang.language, {"y_true": [], "y_pred": []})
        bucket["y_true"].append(ex["label"])
        bucket["y_pred"].append(pred.general_sentiment)
    report = {"overall": precision_recall_f1(y_true, y_pred),
              "by_language": {k: precision_recall_f1(v["y_true"], v["y_pred"])
                              for k, v in per_lang.items()},
              "model": "lexicon-v1", "dataset": str(args.dataset)}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f"written: {args.out}")


def cmd_kronos_export(args):
    from ..event_studies.calendar import TradingCalendar
    from ..integrations.kronos.contract import build_feature_rows, export_frame_json
    conn = _connect(args)
    cal = TradingCalendar.from_file(PROJECT_ROOT / "config" / "trading_calendar.json")
    rows = build_feature_rows(conn, args.ticker, args.entity_id, cal)
    out = args.out or f"data/exports/kronos_features_{args.ticker}.json"
    Path(out).write_text(export_frame_json(rows), encoding="utf-8")
    print(f"exported {len(rows)} feature rows -> {out}")


def cmd_serve(args):
    try:
        import uvicorn  # noqa
    except ImportError:
        print("uvicorn not installed: pip install fastapi uvicorn", file=sys.stderr)
        sys.exit(2)
    from ..api.app import create_app
    app = create_app(args.db)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="market-intelligence")
    p.add_argument("--db", default="data/market_intelligence.db")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("initdb").set_defaults(func=cmd_initdb)

    pr = sub.add_parser("load-registry")
    pr.add_argument("--registry", required=True)
    pr.set_defaults(func=cmd_load_registry)

    pc = sub.add_parser("collect")
    pc.add_argument("--source-id")
    pc.add_argument("--max-sources", type=int, default=10)
    pc.add_argument("--max-items", type=int, default=25)
    pc.add_argument("--dry-run", action="store_true")
    pc.add_argument("--disable-collection", action="store_true")
    pc.set_defaults(func=cmd_collect)

    pe = sub.add_parser("evaluate")
    pe.add_argument("--dataset", required=True)
    pe.add_argument("--out")
    pe.set_defaults(func=cmd_evaluate)

    pk = sub.add_parser("export-kronos-features")
    pk.add_argument("--entity-id", required=True)
    pk.add_argument("--ticker", required=True)
    pk.add_argument("--out")
    pk.set_defaults(func=cmd_kronos_export)

    ps = sub.add_parser("serve")
    ps.add_argument("--port", type=int, default=8080)
    ps.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
