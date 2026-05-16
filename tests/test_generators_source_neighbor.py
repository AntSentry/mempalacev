from mempalace.retrieval.generators.source_neighbor import SourceNeighborGenerator
from mempalace.retrieval.query_frame import extract_query_frame


def test_source_neighbor_requires_scope():
    assert SourceNeighborGenerator().candidates(extract_query_frame("Riley"), 5) == []
    assert SourceNeighborGenerator().candidates(extract_query_frame("Riley", wing="work"), 5)
