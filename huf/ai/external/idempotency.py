from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
	"""Serialize ``obj`` to a deterministic JSON string (sorted keys, compact separators)."""
	return json.dumps(
		obj,
		sort_keys=True,
		separators=(",", ":"),
		ensure_ascii=False,
		default=str,
	)


def args_hash(args: dict | None) -> str:
	"""Return the SHA-256 hex digest of the canonical JSON form of ``args``."""
	return hashlib.sha256((canonical_json(args or {})).encode("utf-8")).hexdigest()


def make_idempotency_key(
	session: Any,
	tool_name: str,
	args: dict | None,
	client_call_id: str | None = None,
) -> str:
	"""Build a stable SHA-256 idempotency key for a tool call within a session."""
	parts = [
		str(session),
		str(tool_name),
		args_hash(args),
		str(client_call_id or ""),
	]
	return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
