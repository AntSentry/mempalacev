CREATE TABLE IF NOT EXISTS gap_event_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor TEXT DEFAULT 'system',
    allowed INTEGER NOT NULL DEFAULT 1,
    requires_evidence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_status, to_status, actor)
);

INSERT OR IGNORE INTO gap_event_transitions (from_status, to_status, actor, allowed, requires_evidence) VALUES
('open', 'resolved', 'system', 1, 1),
('open', 'dismissed', 'system', 1, 0),
('open', 'superseded', 'system', 1, 1),
('open', 'rejected', 'system', 1, 0),
('open', 'resolved', 'user', 1, 1),
('open', 'dismissed', 'user', 1, 0),
('open', 'superseded', 'user', 1, 1),
('open', 'rejected', 'user', 1, 0),
('resolved', 'open', 'user', 1, 0),
('dismissed', 'open', 'user', 1, 0),
('superseded', 'open', 'user', 1, 0),
('rejected', 'open', 'user', 1, 0);
