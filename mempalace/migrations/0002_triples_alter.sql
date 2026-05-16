ALTER TABLE triples ADD COLUMN relation_class TEXT;
ALTER TABLE triples ADD COLUMN polarity INTEGER DEFAULT 1;
ALTER TABLE triples ADD COLUMN supersedes_triple_id TEXT;
ALTER TABLE triples ADD COLUMN supersession_chain_id TEXT;
ALTER TABLE triples ADD COLUMN relation_kind TEXT;
ALTER TABLE triples ADD COLUMN confidence_reason TEXT;
ALTER TABLE triples ADD COLUMN invalidation_reason TEXT;

UPDATE triples
SET relation_class = (
    SELECT kind FROM relation_registry WHERE relation_registry.predicate = triples.predicate
)
WHERE relation_class IS NULL;

CREATE INDEX IF NOT EXISTS idx_triples_relation_class ON triples(relation_class);
CREATE INDEX IF NOT EXISTS idx_triples_polarity ON triples(polarity);
CREATE INDEX IF NOT EXISTS idx_triples_supersedes ON triples(supersedes_triple_id);
CREATE INDEX IF NOT EXISTS idx_triples_supersession_chain ON triples(supersession_chain_id);
CREATE INDEX IF NOT EXISTS idx_triples_relation_kind ON triples(relation_kind);
