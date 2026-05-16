"""Topology axis route generator."""

from mempalace.topology.axis_routes import build_axis_queries, execute_axis_query


class TopologyAxisGenerator:
    name = "topology_axis"

    def candidates(self, query, k: int):
        hits = []
        for orientation_index, axis_query in enumerate(build_axis_queries(query)):
            for hit in execute_axis_query(axis_query, k=max(1, k // 2)):
                adjusted_rank = orientation_index * 100 + hit.rank
                hits.append(type(hit)(hit.route, hit.drawer_id, adjusted_rank, hit.raw_score, hit.reason, hit.payload))
        return sorted(hits, key=lambda item: item.rank)[:k]
