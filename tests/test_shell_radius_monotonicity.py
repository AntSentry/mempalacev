from mempalace.topology.shells import topology_shells


def test_shell_radius_monotonicity():
    previous = set()
    for radius in range(5):
        current = {item.drawer_id for item in topology_shells("d1", radius)}
        assert previous <= current
        previous = current
