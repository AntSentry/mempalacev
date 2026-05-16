from mempalace.retrieval.generators.kg_temporal import KGTemporalGenerator
from mempalace.retrieval.query_frame import extract_query_frame


def test_kg_temporal_generator_uses_entities():
    hits = KGTemporalGenerator().candidates(extract_query_frame("Riley in 2025"), 5)
    assert hits[0].drawer_id == "kg:Riley"
