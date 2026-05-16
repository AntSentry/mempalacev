from mempalace.retrieval.generators.vector import VectorGenerator
from mempalace.retrieval.query_frame import extract_query_frame


def test_vector_generator_returns_ranked_hits():
    hits = VectorGenerator().candidates(extract_query_frame("Riley project"), 5)
    assert hits
    assert [hit.rank for hit in hits] == sorted(hit.rank for hit in hits)
