# MCP Tools Reference

Detailed parameter schemas for all 30 MCP tools.

## Palace — Read Tools

### `mempalace_status`

Palace overview: total drawers, wing and room counts, AAAK spec, and memory protocol.

**Parameters:** None

**Returns:** `{ total_drawers, wings, rooms, protocol, aaak_dialect }`

---

### `mempalace_list_wings`

List all wings with drawer counts.

**Parameters:** None

**Returns:** `{ wings: { "wing_name": count } }`

---

### `mempalace_list_rooms`

List rooms within a wing (or all rooms if no wing given).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing` | string | No | Wing to list rooms for |

**Returns:** `{ wing, rooms: { "room_name": count } }`

---

### `mempalace_get_taxonomy`

Full wing → room → drawer count tree.

**Parameters:** None

**Returns:** `{ taxonomy: { "wing": { "room": count } } }`

---

### `mempalace_search`

Semantic search. Returns verbatim drawer content with similarity scores.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | **Yes** | What to search for |
| `limit` | integer | No | Max results (default: 5) |
| `wing` | string | No | Filter by wing |
| `room` | string | No | Filter by room |

**Returns:** `{ query, filters, results: [{ text, wing, room, source_file, similarity }] }`

---

### `mempalace_check_duplicate`

Check if content already exists in the palace before filing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | **Yes** | Content to check |
| `threshold` | number | No | Similarity threshold 0–1 (default: 0.85–0.87) |

**Returns:** `{ is_duplicate, matches: [{ id, wing, room, similarity, content }] }`

---

### `mempalace_get_aaak_spec`

Returns the AAAK dialect specification.

**Parameters:** None

**Returns:** `{ aaak_spec: "..." }`

---

## Palace — Write Tools

### `mempalace_add_drawer`

File verbatim content into the palace. Identical content (same deterministic drawer ID) is silently skipped. For similarity-based duplicate detection before filing, use `mempalace_check_duplicate`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing` | string | **Yes** | Wing (project name) |
| `room` | string | **Yes** | Room (aspect: backend, decisions, etc.) |
| `content` | string | **Yes** | Verbatim content to store |
| `source_file` | string | No | Where this came from |
| `added_by` | string | No | Who is filing (default: "mcp") |

**Returns:** `{ success, drawer_id, wing, room }`

---

### `mempalace_delete_drawer`

Delete a drawer by ID. Irreversible.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `drawer_id` | string | **Yes** | ID of the drawer to delete |

**Returns:** `{ success, drawer_id }`

---

### `mempalace_sync`

Prune drawers whose source files are gitignored, deleted, or moved. Returns a dry-run report by default; pass `apply=true` to commit deletions.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_dir` | string | No | Project root to scope the sync (auto-detected from drawer metadata if omitted) |
| `wing` | string | No | Limit to one wing |
| `apply` | boolean | No | Actually delete drawers; default is dry-run preview |

**Returns:** `{ scanned, kept, gitignored, missing, no_source, out_of_scope, removed_drawers, removed_closets, dry_run, by_source }`

---

### `mempalace_get_drawer`

Fetch a single drawer by ID — returns full content and metadata.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `drawer_id` | string | **Yes** | ID of the drawer to fetch |

**Returns:** `{ drawer_id, content, wing, room, metadata }` where `metadata.source_file`, when present, is the basename only — the absolute path written by the miners is reduced before the dict is returned to MCP clients.

---

### `mempalace_list_drawers`

List drawers with pagination. Optional wing/room filter. Returns IDs, wings, rooms, and content previews.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing` | string | No | Filter by wing |
| `room` | string | No | Filter by room |
| `limit` | integer | No | Max results per page (default 20, max 100) |
| `offset` | integer | No | Offset for pagination (default 0) |

**Returns:** `{ drawers: [...], total, limit, offset }`

---

### `mempalace_update_drawer`

Update an existing drawer's content and/or metadata (wing, room). Fetches the existing drawer first; returns an error if not found.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `drawer_id` | string | **Yes** | ID of the drawer to update |
| `content` | string | No | New content (omit to keep existing) |
| `wing` | string | No | New wing (omit to keep existing) |
| `room` | string | No | New room (omit to keep existing) |

**Returns:** `{ success, drawer_id, updated_fields }`

---

## Knowledge Graph Tools

### `mempalace_kg_query`

Query entity relationships with time filtering.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity` | string | **Yes** | Entity to query (e.g. "Max", "MyProject") |
| `as_of` | string | No | Date filter — only facts valid at this date (YYYY-MM-DD) |
| `direction` | string | No | `outgoing`, `incoming`, or `both` (default: `both`) |

**Returns:** `{ entity, as_of, facts: [{ direction, subject, predicate, object, valid_from, valid_to, current }], count }`

---

### `mempalace_kg_add`

Add a fact to the knowledge graph.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subject` | string | **Yes** | The entity doing/being something |
| `predicate` | string | **Yes** | Relationship type (e.g. "loves", "works_on") |
| `object` | string | **Yes** | The entity being connected to |
| `valid_from` | string | No | When this became true (YYYY-MM-DD) |
| `source_closet` | string | No | Closet ID where this fact appears |

**Returns:** `{ success, triple_id, fact }`

---

### `mempalace_kg_invalidate`

Mark a fact as no longer true.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subject` | string | **Yes** | Entity |
| `predicate` | string | **Yes** | Relationship |
| `object` | string | **Yes** | Connected entity |
| `ended` | string | No | When it stopped being true (default: today) |

**Returns:** `{ success, fact, ended }`

---

### `mempalace_kg_timeline`

Chronological timeline of facts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity` | string | No | Entity to get timeline for (omit for full timeline) |

**Returns:** `{ entity, timeline: [{ subject, predicate, object, valid_from, valid_to, current }], count }`

---

### `mempalace_kg_stats`

Knowledge graph overview.

**Parameters:** None

**Returns:** `{ entities, triples, current_facts, expired_facts, relationship_types }`

---

## Navigation Tools

### `mempalace_traverse`

Walk the palace graph from a room. Find connected ideas across wings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_room` | string | **Yes** | Room to start from |
| `max_hops` | integer | No | How many connections to follow (default: 2) |

**Returns:** `[{ room, wings, halls, count, hop, connected_via }]`

---

### `mempalace_find_tunnels`

Find rooms that bridge two wings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing_a` | string | No | First wing |
| `wing_b` | string | No | Second wing |

**Returns:** `[{ room, wings, halls, count, recent }]`

---

### `mempalace_graph_stats`

Palace graph overview: nodes, tunnels, edges, connectivity.

**Parameters:** None

**Returns:** `{ total_rooms, tunnel_rooms, total_edges, rooms_per_wing, top_tunnels }`

---

### `mempalace_create_tunnel`

Create a cross-wing tunnel linking two palace locations. Use when content in one project relates to another — e.g., an API design in `project_api` connects to a database schema in `project_database`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_wing` | string | **Yes** | Wing of the source |
| `source_room` | string | **Yes** | Room in the source wing |
| `target_wing` | string | **Yes** | Wing of the target |
| `target_room` | string | **Yes** | Room in the target wing |
| `label` | string | No | Description of the connection |
| `source_drawer_id` | string | No | Specific source drawer ID |
| `target_drawer_id` | string | No | Specific target drawer ID |

**Returns:** `{ success, tunnel_id, source, target }`

---

### `mempalace_list_tunnels`

List all explicit cross-wing tunnels. Optionally filter by wing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing` | string | No | Filter tunnels by wing (source or target) |

**Returns:** `{ tunnels: [...], count }`

---

### `mempalace_delete_tunnel`

Delete an explicit tunnel by its ID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tunnel_id` | string | **Yes** | Tunnel ID to delete |

**Returns:** `{ success, tunnel_id }`

---

### `mempalace_follow_tunnels`

Follow tunnels from a room to see what it connects to in other wings. Returns connected rooms with drawer previews.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wing` | string | **Yes** | Wing to start from |
| `room` | string | **Yes** | Room to follow tunnels from |

**Returns:** `[{ wing, room, label, previews }]`

---

## Agent Diary Tools

### `mempalace_diary_write`

Write to your personal agent diary.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_name` | string | **Yes** | Your name — each agent gets its own wing |
| `entry` | string | **Yes** | Diary entry (in AAAK format recommended) |
| `topic` | string | No | Topic tag (default: "general") |

**Returns:** `{ success, entry_id, agent, topic, timestamp }`

---

### `mempalace_diary_read`

Read recent diary entries.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_name` | string | **Yes** | Your name |
| `last_n` | integer | No | Number of recent entries (default: 10) |

**Returns:** `{ agent, entries: [{ date, timestamp, topic, content }], total, showing }`

---

## System Tools

### `mempalace_hook_settings`

Get or set auto-save hook behaviour. `silent_save=true` saves directly without MCP-level clutter; `silent_save=false` uses the legacy blocking path. `desktop_toast=true` surfaces a desktop notification when a save completes. Call with no arguments to view the current settings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `silent_save` | boolean | No | `true` = silent direct save, `false` = blocking MCP calls |
| `desktop_toast` | boolean | No | `true` = show desktop toast via `notify-send` |

**Returns:** `{ silent_save, desktop_toast }`

---

### `mempalace_memories_filed_away`

Check whether a recent palace checkpoint was saved. Returns message count and timestamp of the last save.

**Parameters:** None

**Returns:** `{ filed, message_count, timestamp }`

---

### `mempalace_reconnect`

Force a reconnect to the palace database. Use this after external scripts or CLI commands modified the palace directly, which can leave the in-memory HNSW index stale.

**Parameters:** None

**Returns:** `{ success, message, drawers, vector_disabled[, vector_disabled_reason] }` (on no-palace: `{ success: false, message, drawers, vector_disabled }`; on exception: `{ success: false, error }`)

---

## Topology Layer Tools

These tools belong to the experimental topology layer. All are gated by env flags (default off) and require explicit opt-in. Retrieval-quality effects are not claimed; see `MEMPALACE_TOPOLOGY_SPEC.md` for status.

### `mempalace_gap_list`

List knowledge-graph gap events — transitions, supersessions, and unresolved contradictions tracked in the gap graph. Gated by `MEMPALACE_ENABLE_GAP_GRAPH=1`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subject` | string | No | Filter to gap events whose subject matches |
| `gap_type` | string | No | Filter by status: `open`, `resolved`, `superseded`, `rejected` |
| `limit` | integer | No | Maximum events returned (default: 20) |

**Returns:** list of gap event records (or `{ error: "mempalace_gap_list requires MEMPALACE_ENABLE_GAP_GRAPH=1" }` when the flag is off)

---

### `mempalace_gap_resolve`

Transition a gap event with required evidence. Validates against the gap-event state-machine table; rejects illegal transitions. Gated by `MEMPALACE_ENABLE_GAP_GRAPH=1`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `gap_id` | string | **Yes** | The id of the gap event to transition |
| `to_status` | string | **Yes** | Target status: `resolved`, `superseded`, `rejected`, or `open` (re-open) |
| `evidence_drawer_id` | string | No | Drawer id documenting the resolution (required for most transitions) |
| `rationale` | string | No | Free-text rationale, persisted with the transition |
| `status` | string | No | Alias for `to_status` |
| `note` | string | No | Alias for `rationale` |

**Returns:** updated gap event record, or `{ success: false, error: ... }` on illegal transition or when flag is off

---

### `mempalace_trace_recall`

Return a retrieval trace showing which routes surfaced each memory. The trace includes per-route attribution, the top result, supporting / contradicting / stale partitions, and a confidence label. Gated by `MEMPALACE_ENABLE_TRACE=1`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | **Yes** | The query text to trace |
| `wing` | string | No | Restrict trace to a wing |
| `k` | integer | No | Top-K results to attribute (default: 10) |
| `include_stale` | boolean | No | Include stale drawers in the returned trace (default: false) |
| `limit` | integer | No | Maximum result count (alias for `k`) |

**Returns:** `{ query, top_drawer_id, routes: [{ route, rank, reason, raw_score }], supporting: [drawer_id], contradicting: [drawer_id], stale: [drawer_id], confidence }`. Raises `NotImplementedError` when the flag is off.

---

### `mempalace_search_with_mode`

Search the palace using one of the closed-form query modes from RFC T3b. The mode selects a deterministic combination of step size, ray count, polarity filter, and status filter; the unbounded query string is replaced by a small named palette of query shapes. Gated by `MEMPALACE_ENABLE_QUERY_MODES=1`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mode` | string | **Yes** | One of: `direct_recall`, `summary_view`, `contrast_view`, `mirror_view`, `family_view`, `polar_view` |

**Returns:** list of ranked candidates filtered/shaped per the selected mode, or `{ error: "mempalace_search_with_mode requires MEMPALACE_ENABLE_QUERY_MODES=1" }` when the flag is off.

---

### `mempalace_list_query_modes`

List the closed-form query modes available at the MCP boundary together with their flag-set mappings (RFC T3b). Use this to discover what `mempalace_search_with_mode` accepts. Gated by `MEMPALACE_ENABLE_QUERY_MODES=1`.

**Parameters:** None

**Returns:** list of `{ mode, description, flags }` entries, or `{ error: "mempalace_list_query_modes requires MEMPALACE_ENABLE_QUERY_MODES=1" }` when the flag is off.
