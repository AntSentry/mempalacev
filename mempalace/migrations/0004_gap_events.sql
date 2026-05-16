CREATE TABLE IF NOT EXISTS gap_events (
    id TEXT PRIMARY KEY,
    gap_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    subject TEXT,
    predicate TEXT,
    object TEXT,
    old_object TEXT,
    new_object TEXT,
    old_drawer_id TEXT,
    new_drawer_id TEXT,
    triple_id TEXT,
    conflicting_triple_id TEXT,
    triggered_by_triple_id TEXT,
    detected_by TEXT,
    confidence REAL DEFAULT 1.0,
    supersession_chain_id TEXT,
    details TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    resolution_note TEXT,
    evidence_drawer_id TEXT,
    rationale TEXT
);

CREATE INDEX IF NOT EXISTS idx_gap_events_status ON gap_events(status);
CREATE INDEX IF NOT EXISTS idx_gap_events_subject_predicate ON gap_events(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_gap_events_type ON gap_events(gap_type);
CREATE INDEX IF NOT EXISTS idx_gap_events_chain ON gap_events(supersession_chain_id);
