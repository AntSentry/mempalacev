from mempalace.retrieval.fusion import RouteHit, rrf_score


def test_empty_returns_empty():
    assert rrf_score([]) == []


def test_single_route_preserves_order():
    ranked = rrf_score([RouteHit("a", "d1", 1), RouteHit("a", "d2", 2)])
    assert [item.drawer_id for item in ranked] == ["d1", "d2"]


def test_two_routes_agreeing_correct_order():
    ranked = rrf_score([
        RouteHit("a", "d1", 1),
        RouteHit("b", "d1", 2),
        RouteHit("a", "d2", 2),
    ])
    assert ranked[0].drawer_id == "d1"
    assert ranked[0].route_count == 2


def test_weight_zero_excludes():
    ranked = rrf_score([RouteHit("a", "d1", 1), RouteHit("b", "d2", 1)], route_weights={"a": 0, "b": 1})
    assert [item.drawer_id for item in ranked] == ["d2"]
