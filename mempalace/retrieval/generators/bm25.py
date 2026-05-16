"""BM25 route wrapper."""

from ..fusion import RouteHit


class BM25Generator:
    name = "bm25"

    def candidates(self, query, k: int):
        terms = query.topics or query.text.split()
        if not terms:
            return []
        return [RouteHit(self.name, f"bm25:{':'.join(terms[:4])}", 1, reason="bm25 lexical match", payload={"terms": terms})][:k]
