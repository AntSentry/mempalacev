"""Gap-event retrieval route."""

from pathlib import Path
import re

from ..fusion import RouteHit


def _patterns():
    path = Path(__file__).resolve().parents[1] / "gap_query_patterns.txt"
    patterns = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(re.compile(stripped))
    return patterns


def is_gap_query(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _patterns())


class GapGenerator:
    name = "gap"

    def candidates(self, query, k: int):
        if not is_gap_query(query.text):
            return []
        entities = query.entities_extracted or ["query"]
        return [
            RouteHit(self.name, f"gap:{entity}", rank, reason="gap-language query", payload={"entity": entity})
            for rank, entity in enumerate(entities[:k], start=1)
        ]
