from mempalace.retrieval.generators.bm25 import BM25Generator
from mempalace.retrieval.query_frame import extract_query_frame


def test_bm25_generator_returns_ranked_hits():
    hits = BM25Generator().candidates(extract_query_frame("Riley project"), 5)
    assert hits
    assert hits[0].route == "bm25"
