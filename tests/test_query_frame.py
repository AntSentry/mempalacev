from mempalace.retrieval.query_frame import extract_query_frame


def test_query_frame_extracts_entities_and_time():
    frame = extract_query_frame("Where does Riley work in 2025?", wing="work")
    assert "Riley" in frame.entities_extracted
    assert frame.as_of == "2025"
    assert frame.wing == "work"


def test_query_frame_empty_query():
    frame = extract_query_frame("")
    assert frame.text == ""
    assert frame.entities_extracted == []
