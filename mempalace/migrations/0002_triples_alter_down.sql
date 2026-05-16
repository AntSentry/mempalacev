DROP INDEX IF EXISTS idx_triples_relation_kind;
DROP INDEX IF EXISTS idx_triples_relation_class;
DROP INDEX IF EXISTS idx_triples_polarity;
DROP INDEX IF EXISTS idx_triples_supersedes;
DROP INDEX IF EXISTS idx_triples_supersession_chain;

CREATE TABLE triples__rollback AS
SELECT id, subject, predicate, object, valid_from, valid_to, confidence,
       source_closet, source_file, source_drawer_id, adapter_name, extracted_at
FROM triples;

DROP TABLE triples;

CREATE TABLE triples (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    confidence REAL DEFAULT 1.0,
    source_closet TEXT,
    source_file TEXT,
    source_drawer_id TEXT,
    adapter_name TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject) REFERENCES entities(id),
    FOREIGN KEY (object) REFERENCES entities(id)
);

INSERT INTO triples SELECT * FROM triples__rollback;
DROP TABLE triples__rollback;

CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject);
CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object);
CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
CREATE INDEX IF NOT EXISTS idx_triples_valid ON triples(valid_from, valid_to);
