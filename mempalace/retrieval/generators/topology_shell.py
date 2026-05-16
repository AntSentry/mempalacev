"""Topology shell route generator."""

from mempalace.retrieval.fusion import RouteHit
from mempalace.topology.shells import topology_shells


class TopologyShellGenerator:
    name = "topology_shell"

    def candidates(self, query, k: int):
        center = query.entities_extracted[0] if query.entities_extracted else query.text[:32] or "query"
        hits = []
        for item in topology_shells(center, 4):
            hits.append(RouteHit(self.name, item.drawer_id, item.radius + 1, reason=item.reason, payload={"radius": item.radius}))
        return hits[:k]
