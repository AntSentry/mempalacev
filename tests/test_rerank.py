from mempalace.retrieval.rerank import no_op_rerank


def test_no_op_rerank_preserves_order():
    assert no_op_rerank(["a", "b"]) == ["a", "b"]
