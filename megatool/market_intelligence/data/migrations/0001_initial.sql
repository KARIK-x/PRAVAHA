-- Migration 0001: initial schema for the NEPSE Market Intelligence Engine.
-- SQLite, WAL mode recommended at connection time.
-- Conventions: TEXT primary keys (stable hashes/uuids); timestamps as UTC
-- ISO-8601 TEXT; NULL means missing (never 0 or '').

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    primary_domain TEXT NOT NULL,
    canonical_homepage TEXT,
    source_group TEXT NOT NULL,          -- A | B | C
    source_type TEXT,                    -- portal | official | regulator | international ...
    country_or_region TEXT,
    primary_language TEXT,
    additional_languages TEXT,
    subject_categories TEXT,             -- JSON array
    nepse_relevance TEXT,                -- high | medium | low
    rss_url TEXT,
    rss_available INTEGER,               -- 1/0/NULL=unknown
    official_api_available INTEGER,
    sitemap_available INTEGER,
    automated_access_status TEXT,        -- DISCOVERED|VERIFIED|APPROVED|REVIEW_REQUIRED|BLOCKED|UNAVAILABLE|STALE|RETIRED
    terms_review_status TEXT,
    robots_policy_review TEXT,
    source_quality_notes TEXT,
    last_verified_at TEXT,
    last_successful_fetch_at TEXT,
    expected_update_interval TEXT,
    implementation_status TEXT,          -- implemented | pending | not_implemented
    error_status TEXT,
    confidence_level TEXT,
    evidence_urls TEXT,                  -- JSON array
    researcher_notes TEXT
);

CREATE TABLE IF NOT EXISTS source_access_reviews (
    review_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    reviewed_at TEXT NOT NULL,
    reviewer TEXT,
    decision TEXT NOT NULL,              -- approved | rejected | needs_review
    access_method TEXT,
    restrictions TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    checked_at TEXT NOT NULL,
    http_status INTEGER,
    latency_ms INTEGER,
    ok INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (source_id, checked_at)
);

CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,         -- sha256(source_id + canonical_url)
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    normalized_text TEXT,
    content_hash TEXT NOT NULL,          -- sha256 of normalized text
    language TEXT,
    language_confidence REAL,
    author TEXT,
    published_at TEXT,                   -- UTC ISO or NULL
    retrieved_at TEXT NOT NULL,
    collection_method TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    UNIQUE (source_id, canonical_url)
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);

CREATE TABLE IF NOT EXISTS article_versions (
    article_id TEXT NOT NULL REFERENCES articles(article_id),
    version INTEGER NOT NULL,
    body TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (article_id, version)
);

CREATE TABLE IF NOT EXISTS article_duplicates (
    duplicate_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL REFERENCES articles(article_id),
    duplicate_of TEXT NOT NULL REFERENCES articles(article_id),
    similarity REAL,
    method TEXT NOT NULL,                -- canonical_url|exact_text_hash|normalized_text_hash|shingle_jaccard
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_accounts (
    account_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    display_name TEXT,
    handle TEXT NOT NULL,
    profile_url TEXT,
    account_category TEXT,
    organization TEXT,
    primary_topic TEXT,
    nepse_relevance TEXT,
    primary_language TEXT,
    public_verification_status TEXT,     -- verified|unverified|unknown
    official_website_linked INTEGER,
    source_of_discovery TEXT,
    verification_evidence TEXT,
    account_status TEXT,                 -- active|suspended|unknown
    collection_method TEXT,
    access_status TEXT,
    follower_count INTEGER,              -- NULL when not legitimately known
    follower_count_observation_date TEXT,
    relevance_score REAL,
    credibility_assessment TEXT,
    confidence_level TEXT,
    last_verified_at TEXT,
    researcher_notes TEXT,
    UNIQUE (platform, handle)
);

CREATE TABLE IF NOT EXISTS social_posts (
    post_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES social_accounts(account_id),
    platform TEXT NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT,
    content_hash TEXT NOT NULL,
    language TEXT,
    language_confidence REAL,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    url TEXT,
    UNIQUE (platform, post_id)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    official_name TEXT NOT NULL,
    ticker TEXT,
    exchange TEXT DEFAULT 'NEPSE',
    sector TEXT,
    nepali_name TEXT,
    verification_status TEXT DEFAULT 'unverified'
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    alias TEXT NOT NULL,
    alias_type TEXT,                     -- official|english|devanagari|romanized|former|colloquial
    UNIQUE (entity_id, alias)
);

CREATE TABLE IF NOT EXISTS article_entity_mentions (
    article_id TEXT NOT NULL REFERENCES articles(article_id),
    entity_id TEXT REFERENCES entities(entity_id),
    matched_alias TEXT NOT NULL,
    confidence REAL NOT NULL,
    role TEXT DEFAULT 'mentioned',       -- subject|mentioned
    status TEXT NOT NULL,                -- resolved|ambiguous|unresolved
    candidates TEXT,                     -- JSON array for ambiguous
    PRIMARY KEY (article_id, entity_id, matched_alias)
);

CREATE TABLE IF NOT EXISTS post_entity_mentions (
    post_id TEXT NOT NULL REFERENCES social_posts(post_id),
    entity_id TEXT REFERENCES entities(entity_id),
    matched_alias TEXT NOT NULL,
    confidence REAL NOT NULL,
    role TEXT DEFAULT 'mentioned',
    status TEXT NOT NULL,
    candidates TEXT,
    PRIMARY KEY (post_id, entity_id, matched_alias)
);

CREATE TABLE IF NOT EXISTS sentiment_results (
    result_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,           -- article|post
    target_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    general_sentiment TEXT NOT NULL,
    intensity TEXT NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    language TEXT,
    details TEXT,                        -- JSON
    processed_at TEXT NOT NULL,
    UNIQUE (target_type, target_id, model_id, model_version)
);
CREATE INDEX IF NOT EXISTS idx_sentiment_target ON sentiment_results(target_type, target_id);

CREATE TABLE IF NOT EXISTS sentiment_model_registry (
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    description TEXT,
    languages TEXT,
    status TEXT,                         -- active|experimental|deprecated
    PRIMARY KEY (model_id, model_version)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_title TEXT NOT NULL,
    event_summary TEXT,
    primary_entities TEXT,               -- JSON array of entity_ids
    affected_sectors TEXT,               -- JSON array
    potential_market_scope TEXT,
    publication_time TEXT,
    detection_time TEXT NOT NULL,
    first_observed_time TEXT,
    confirmation_status TEXT NOT NULL DEFAULT 'unverified_claim',
    sentiment_by_entity TEXT,            -- JSON
    distinct_source_count INTEGER DEFAULT 0,
    distinct_author_count INTEGER DEFAULT 0,
    expected_transmission_channels TEXT,
    uncertainty TEXT,
    analyst_review_status TEXT DEFAULT 'pending',
    taxonomy_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(first_observed_time);

CREATE TABLE IF NOT EXISTS event_sources (
    event_id TEXT NOT NULL REFERENCES events(event_id),
    article_id TEXT REFERENCES articles(article_id),
    post_id TEXT REFERENCES social_posts(post_id),
    added_at TEXT NOT NULL,
    PRIMARY KEY (event_id, article_id, post_id)
);

CREATE TABLE IF NOT EXISTS event_entities (
    event_id TEXT NOT NULL REFERENCES events(event_id),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    role TEXT DEFAULT 'affected',
    PRIMARY KEY (event_id, entity_id)
);

CREATE TABLE IF NOT EXISTS event_clusters (
    cluster_id TEXT PRIMARY KEY,
    canonical_event_id TEXT NOT NULL REFERENCES events(event_id),
    member_event_id TEXT NOT NULL REFERENCES events(event_id),
    similarity REAL,
    method TEXT
);

CREATE TABLE IF NOT EXISTS translations (
    translation_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    source_language TEXT,
    target_language TEXT NOT NULL,
    translation_method TEXT NOT NULL,
    translation_model TEXT,
    translation_version TEXT,
    translated_at TEXT NOT NULL,
    confidence REAL,
    limitations TEXT
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,              -- rss|api|social|backfill
    source_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,                -- running|success|failed|partial|dry_run
    records_fetched INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    records_duplicate INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS collection_errors (
    error_id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES collection_jobs(job_id),
    source_id TEXT,
    occurred_at TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_checks (
    check_id TEXT PRIMARY KEY,
    checked_at TEXT NOT NULL,
    check_type TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    severity TEXT NOT NULL,              -- info|warning|error
    message TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,              -- event_study|evaluation|sentiment_batch
    started_at TEXT NOT NULL,
    finished_at TEXT,
    parameters TEXT,                     -- JSON
    status TEXT NOT NULL,
    result_summary TEXT                  -- JSON
);

CREATE TABLE IF NOT EXISTS event_studies (
    study_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES analysis_runs(run_id),
    event_id TEXT NOT NULL,
    entity_id TEXT,
    window_sessions INTEGER NOT NULL,
    event_session_date TEXT,
    return_pct REAL,
    benchmark_return_pct REAL,
    excess_return_pct REAL,
    volume_change_pct REAL,
    data_status TEXT NOT NULL,           -- ok|missing_prices|insufficient_history
    notes TEXT
);

CREATE TABLE IF NOT EXISTS market_prices (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,            -- YYYY-MM-DD (NEPSE session date)
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, turnover REAL,
    source TEXT NOT NULL,                -- data provenance (adapter id)
    ingested_at TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS model_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    language TEXT,
    metrics TEXT NOT NULL,               -- JSON: precision/recall/f1/macro_f1/...
    sample_count INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS source_registry_versions (
    version_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    source_count INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT
);
