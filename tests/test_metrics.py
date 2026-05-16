from eval.metrics import f1, mrr, recall_at_k


def test_metrics():
    assert recall_at_k(["a", "b"], ["b", "c"], 2) == 0.5
    assert mrr(["a", "b"], ["b"]) == 0.5
    assert round(f1(["a"], ["a", "b"]), 3) == 0.667
