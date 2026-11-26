"""Helpers for listing the indexed chunks of one input (``KnowledgeBackend.get_chunks``)."""

import json
from typing import Any

from . import ChunkResult

MAX_LISTED_CHUNKS = 10000


def to_result(
	chunk_id: str | None,
	text: str | None,
	metadata: dict[str, Any] | None,
	title: str | None = None,
	chunk_index: int | None = None,
) -> ChunkResult:
	"""Normalize one stored chunk; ``metadata["chunk_index"]`` is set whenever it is known."""
	meta = dict(metadata or {})
	if chunk_index is None:
		chunk_index = meta.get("chunk_index")
	if chunk_index is not None:
		try:
			meta["chunk_index"] = int(chunk_index)
		except (TypeError, ValueError):
			meta.pop("chunk_index", None)
	return ChunkResult(chunk_id=str(chunk_id or ""), text=text or "", title=title, metadata=meta)


def _order_key(chunk: ChunkResult) -> int:
	return int((chunk.metadata or {}).get("chunk_index", 0) or 0)


def page_chunks(chunks: list[ChunkResult], start: int, limit: int) -> tuple[list[ChunkResult], int]:
	"""Order chunks by position and slice one page. Returns ``(page, total)``."""
	ordered = sorted(chunks, key=_order_key)
	start = max(int(start), 0)
	return ordered[start : start + max(int(limit), 0)], len(ordered)


def parse_json_metadata(raw: Any) -> dict[str, Any]:
	if not raw:
		return {}
	if isinstance(raw, dict):
		return dict(raw)
	try:
		value = json.loads(raw)
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


def sql_chunks(conn: Any, input_id: str, start: int, limit: int) -> tuple[list[ChunkResult], int]:
	"""Page the ``chunks`` table shared by the SQLite backends."""
	total = conn.execute("SELECT COUNT(*) FROM chunks WHERE input_id = ?", (input_id,)).fetchone()[0]
	rows = conn.execute(
		"SELECT chunk_id, text, source_title, chunk_index, metadata FROM chunks "
		"WHERE input_id = ? ORDER BY chunk_index LIMIT ? OFFSET ?",
		(input_id, max(int(limit), 0), max(int(start), 0)),
	).fetchall()
	return [
		to_result(
			r["chunk_id"], r["text"], parse_json_metadata(r["metadata"]), r["source_title"], r["chunk_index"]
		)
		for r in rows
	], int(total)


def zvec_chunks(backend: Any, input_id: str, start: int, limit: int) -> tuple[list[ChunkResult], int]:
	"""Page the chunks of one input from a zvec collection (filter-only query)."""
	from .zvec_backend import _quote_filter_value

	topk = min(max(backend._doc_count(), 1), MAX_LISTED_CHUNKS)
	docs = backend.collection.query(
		filter=f"input_id = {_quote_filter_value(input_id)}",
		topk=topk,
		output_fields=["text", "source_title", "chunk_index", "metadata_json"],
	)
	chunks = [
		to_result(
			d.id,
			d.fields.get("text"),
			parse_json_metadata(d.fields.get("metadata_json")),
			d.fields.get("source_title"),
			d.fields.get("chunk_index"),
		)
		for d in docs
	]
	return page_chunks(chunks, start, limit)
