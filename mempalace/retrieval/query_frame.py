"""Query-frame extraction for topology retrieval routes."""

from dataclasses import dataclass, field
import re
from typing import List, Optional, Tuple


_DATE_RE = re.compile(r"\b(20\d{2}(?:-\d{2})?(?:-\d{2})?)\b")
_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_'-]{2,}\b")
_STOP_ENTITIES = {"What", "When", "Where", "Why", "How", "Who", "Current", "Before", "After", "Today"}


@dataclass(frozen=True)
class QueryFrame:
    """Normalized query input shared by route generators."""

    text: str
    wing: Optional[str] = None
    room: Optional[str] = None
    entities_extracted: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    time_window: Optional[Tuple[str, str]] = None
    as_of: Optional[str] = None


def extract_query_frame(text: str, wing: str = None, room: str = None) -> QueryFrame:
    """Extract a lightweight, deterministic query frame from natural language."""

    query = (text or "").strip()
    entities = []
    for match in _ENTITY_RE.findall(query):
        if match not in _STOP_ENTITIES and match not in entities:
            entities.append(match)

    dates = _DATE_RE.findall(query)
    time_window = None
    as_of = None
    if dates:
        as_of = dates[-1]
        time_window = (dates[0], dates[-1])

    tokens = [tok.lower() for tok in re.findall(r"[A-Za-z][A-Za-z0-9_'-]{2,}", query)]
    topics = []
    for tok in tokens:
        if tok.title() in entities or tok in {"what", "when", "where", "why", "how", "who", "the", "and", "for"}:
            continue
        if tok not in topics:
            topics.append(tok)

    return QueryFrame(
        text=query,
        wing=wing,
        room=room,
        entities_extracted=entities,
        topics=topics[:8],
        time_window=time_window,
        as_of=as_of,
    )
