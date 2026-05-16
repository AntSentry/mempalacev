"""Source-neighbor route wrapper."""

from ..fusion import RouteHit


class SourceNeighborGenerator:
    name = "source_neighbor"

    def candidates(self, query, k: int):
        if not query.room and not query.wing:
            return []
        key = query.room or query.wing
        return [RouteHit(self.name, f"neighbor:{key}", 1, reason="source neighbor context", payload={"scope": key})][:k]
