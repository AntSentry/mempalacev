from mempalace.retrieval.generators.gap import GapGenerator, is_gap_query
from mempalace.retrieval.query_frame import extract_query_frame


def test_gap_language_query_triggers():
    assert is_gap_query("why did we switch tools")


def test_non_gap_language_query_empty():
    assert GapGenerator().candidates(extract_query_frame("find Riley notes"), 5) == []


def test_gap_generator_surfaces_entities():
    hits = GapGenerator().candidates(extract_query_frame("what changed for Riley now"), 5)
    assert hits and hits[0].drawer_id == "gap:Riley"
