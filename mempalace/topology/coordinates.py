"""Deterministic topology-coordinate computation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from .nexus import family, nexus_label, polarity


COMPUTER_VERSION = "topology-coordinates-v1"


@dataclass(frozen=True)
class DrawerRecord:
    """Minimal drawer-like record accepted by topology coordinate computation."""

    drawer_id: str
    entities: List[str]
    topics: List[str]
    timestamp: str
    speakers: List[str]
    valid_from: str
    valid_to: Optional[str] = None


@dataclass(frozen=True)
class TopologyMeta:
    drawer_id: str
    entity_q: int
    topic_q: int
    time_q: int
    speaker_q: int
    validity_q: int
    nexus_label: int
    family: int
    polarity: int
    primary_axis: str
    computer_version: str = COMPUTER_VERSION


def _canonical_list(values: Iterable[str]) -> bytes:
    normalized = sorted(str(value).strip().lower() for value in values if str(value).strip())
    return "\0".join(normalized).encode("utf-8")


def canonical_entity_set(entities: List[str]) -> bytes:
    """Return sorted, lowercased, NUL-joined entity bytes."""

    return _canonical_list(entities)


def canonical_topic(topics: List[str]) -> bytes:
    return _canonical_list(topics)


def canonical_time(timestamp: str) -> bytes:
    return str(timestamp or "").strip().encode("utf-8")


def canonical_speaker(speakers: List[str]) -> bytes:
    return _canonical_list(speakers)


def canonical_validity(valid_from: str, valid_to: Optional[str]) -> bytes:
    return f"{valid_from or ''}\0{valid_to or ''}".encode("utf-8")


def topology_coord(value_bytes: bytes, salt: bytes) -> int:
    """Return ``blake2b(value_bytes, key=salt, digest_size=4)`` as uint mod 18."""

    digest = hashlib.blake2b(value_bytes, key=salt, digest_size=4).digest()
    return int.from_bytes(digest, "big") % 18


def _field(drawer: Any, attr: str, default: Any) -> Any:
    if isinstance(drawer, dict):
        return drawer.get(attr, default)
    return getattr(drawer, attr, default)


def compute_topology_meta(drawer: Any, palace_salt: bytes) -> TopologyMeta:
    """Compute all five coordinate fields plus derived label, family, and polarity."""

    drawer_id = str(_field(drawer, "drawer_id", _field(drawer, "id", "")))
    coords = {
        "entity_q": topology_coord(canonical_entity_set(_field(drawer, "entities", [])), palace_salt),
        "topic_q": topology_coord(canonical_topic(_field(drawer, "topics", [])), palace_salt),
        "time_q": topology_coord(canonical_time(_field(drawer, "timestamp", "")), palace_salt),
        "speaker_q": topology_coord(canonical_speaker(_field(drawer, "speakers", [])), palace_salt),
        "validity_q": topology_coord(
            canonical_validity(_field(drawer, "valid_from", ""), _field(drawer, "valid_to", None)),
            palace_salt,
        ),
    }
    primary_axis = min(coords.items(), key=lambda item: (item[1], item[0]))[0].replace("_q", "")
    label = nexus_label(coords["entity_q"])
    return TopologyMeta(
        drawer_id=drawer_id,
        nexus_label=label,
        family=family(label),
        polarity=polarity(coords["entity_q"]),
        primary_axis=primary_axis,
        **coords,
    )

