"""Topology retrieval route registry."""

import os
from typing import List, Protocol

from .fusion import RouteHit
from .query_frame import QueryFrame


class RouteGenerator(Protocol):
    name: str

    def candidates(self, query: QueryFrame, k: int) -> List[RouteHit]:
        ...


def default_generators() -> list:
    """Return the baseline Phase 3 generator set."""

    from .generators.bm25 import BM25Generator
    from .generators.gap import GapGenerator
    from .generators.kg_temporal import KGTemporalGenerator
    from .generators.source_neighbor import SourceNeighborGenerator
    from .generators.vector import VectorGenerator

    generators = [VectorGenerator(), BM25Generator(), KGTemporalGenerator(), GapGenerator(), SourceNeighborGenerator()]
    if os.environ.get("MEMPALACE_ENABLE_TOPOLOGY_ROUTES", "").lower() in {"1", "true", "yes", "on"}:
        from .generators.topology_axis import TopologyAxisGenerator
        from .generators.topology_shell import TopologyShellGenerator

        generators.extend([TopologyAxisGenerator(), TopologyShellGenerator()])
    return generators
