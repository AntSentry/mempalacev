from mempalace.retrieval.fusion import RouteHit, rrf_score


def test_order_independence_for_same_route_ranks():
    hits = [RouteHit("a", "d1", 1), RouteHit("b", "d2", 1), RouteHit("c", "d1", 2)]
    reversed_hits = list(reversed(hits))
    assert [item.drawer_id for item in rrf_score(hits)] == [item.drawer_id for item in rrf_score(reversed_hits)]


def test_tie_break_stable():
    ranked = rrf_score([RouteHit("a", "d2", 1), RouteHit("a", "d1", 1)])
    assert [item.drawer_id for item in ranked] == ["d1", "d2"]
