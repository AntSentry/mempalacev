CREATE TABLE IF NOT EXISTS relation_registry (
    predicate TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'semantic',
    inverse_predicate TEXT,
    symmetric INTEGER NOT NULL DEFAULT 0,
    transitive INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO relation_registry (predicate, kind, inverse_predicate, symmetric, transitive, notes) VALUES
('married_to', 'family', 'married_to', 1, 0, 'Symmetric spouse relationship'),
('sibling_of', 'family', 'sibling_of', 1, 0, 'Symmetric sibling relationship'),
('child_of', 'family', 'parent_of', 0, 0, 'Child to parent'),
('parent_of', 'family', 'child_of', 0, 0, 'Parent to child'),
('succeeded_by', 'temporal', 'predecessor_of', 0, 0, 'Replacement or succession'),
('predecessor_of', 'temporal', 'succeeded_by', 0, 0, 'Prior state or predecessor'),
('works_on', 'semantic', NULL, 0, 0, 'Entity works on a project/topic'),
('prefers', 'semantic', NULL, 0, 0, 'Preference relation'),
('opposes', 'semantic', NULL, 0, 0, 'Opposition relation'),
('alternative_to', 'semantic', 'alternative_to', 1, 0, 'Mutual alternative relation');
