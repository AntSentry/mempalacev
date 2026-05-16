CREATE TABLE IF NOT EXISTS wing_sequence (
    wing TEXT NOT NULL,
    drawer_id TEXT NOT NULL,
    sequence_index INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (wing, drawer_id)
);

CREATE INDEX IF NOT EXISTS idx_wing_sequence_order ON wing_sequence(wing, sequence_index);
