from mempalace.retrieval.query_frame import extract_query_frame
from mempalace.topology.axis_routes import build_axis_queries


def test_axis_orientations_distinct():
    orientations = {query.orientation for query in build_axis_queries(extract_query_frame("Riley project"))}
    assert len(orientations) == 6
