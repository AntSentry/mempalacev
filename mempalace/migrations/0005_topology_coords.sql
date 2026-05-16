CREATE TABLE IF NOT EXISTS topology_coords (
    drawer_id TEXT PRIMARY KEY,
    entity_q INTEGER NOT NULL,
    topic_q INTEGER NOT NULL,
    time_q INTEGER NOT NULL,
    speaker_q INTEGER NOT NULL,
    validity_q INTEGER NOT NULL,
    nexus_label INTEGER NOT NULL,
    family INTEGER NOT NULL,
    polarity INTEGER NOT NULL,
    primary_axis TEXT NOT NULL,
    computer_version TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_topology_coords_entity_q ON topology_coords(entity_q);
CREATE INDEX IF NOT EXISTS idx_topology_coords_label ON topology_coords(nexus_label);
