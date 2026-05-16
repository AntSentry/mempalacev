"""Temporal knowledge-graph route wrapper."""

from ..fusion import RouteHit


class KGTemporalGenerator:
    name = "kg_temporal"

    def candidates(self, query, k: int):
        hits = []
        for idx, entity in enumerate(query.entities_extracted[:k], start=1):
            hits.append(RouteHit(self.name, f"kg:{entity}", idx, reason="temporal KG entity match", payload={"entity": entity}))
        return hits
