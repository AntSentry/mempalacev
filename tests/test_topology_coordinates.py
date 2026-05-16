from mempalace.topology.coordinates import (
    DrawerRecord,
    canonical_entity_set,
    compute_topology_meta,
    topology_coord,
)


def test_canonical_entity_set_sorts_lowercases_and_nul_joins():
    assert canonical_entity_set([" Alice ", "bob", "alice"]) == b"alice\0alice\0bob"


def test_topology_coord_is_deterministic():
    assert topology_coord(b"value", b"salt") == topology_coord(b"value", b"salt")


def test_topology_coord_salt_isolation():
    value = b"stable drawer value"
    assert topology_coord(value, b"salt-a") != topology_coord(value, b"salt-b")


def test_compute_topology_meta_is_deterministic_for_same_drawer_and_salt():
    drawer = DrawerRecord(
        drawer_id="drawer-1",
        entities=["Alice", "Bob"],
        topics=["Memory", "Topology"],
        timestamp="2026-05-15T00:00:00Z",
        speakers=["mempalace"],
        valid_from="2026-05-15",
        valid_to=None,
    )
    first = compute_topology_meta(drawer, b"palace-salt")
    second = compute_topology_meta(drawer, b"palace-salt")
    assert first == second
    for value in [first.entity_q, first.topic_q, first.time_q, first.speaker_q, first.validity_q]:
        assert 0 <= value <= 17
    assert 1 <= first.nexus_label <= 9
    assert first.family in {1, 2, 3}
    assert first.polarity in {-1, 1}

