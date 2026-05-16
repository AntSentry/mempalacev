"""Vector route wrapper."""

from ..fusion import RouteHit


class VectorGenerator:
    name = "vector"

    def candidates(self, query, k: int):
        # The production vector route is supplied by searcher integration. This
        # deterministic fallback keeps the protocol usable in isolated tests.
        if not query.text:
            return []
        return [RouteHit(self.name, f"vector:{query.text[:64]}", 1, reason="vector similarity", payload={"text": query.text})][:k]
