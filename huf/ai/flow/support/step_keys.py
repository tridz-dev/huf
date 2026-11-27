"""Idempotent step keys and the run's step ledger (H-W2-13, CONTRACTS.md section 12).

``step_key(run_id, node_id, attempt)`` is opaque, deterministic and at most 64 characters. A re-delivered job (worker
crash, double wake) computes the same key; an explicit retry (new attempt) computes a new one. A node visited again by
a loop folds the visit into ``attempt``: the visit is the number of times the run's cursor already LEFT the node
after completing it, so a re-delivery before the cursor moved (even after the result was recorded) keeps the key and
a later loop visit gets a new one.

The ledger lives in the run context under ``_huf_steps`` =
``{"visits": {node_id: n}, "open": {node_id: step_key}, "done": {step_key: result}}``.
A side-effecting executor calls :func:`replay` first (a completed step returns its recorded result, no side effect
again) and :func:`record` after it succeeded; the engine calls :func:`advance` when it saves the cursor.
Pure: no frappe import.
"""

import hashlib

LEDGER_KEY = "_huf_steps"
NODE_KEY = "_step_key"  # set on the node copy the engine hands to the executor
VISIT_STRIDE = 100  # above nodes.retry.MAX_ATTEMPTS: (visit, retry attempt) never collide


def step_key(run_id: str, node_id: str, attempt: int) -> str:
	"""Opaque deterministic key for one try of one node in one run (64 hex chars)."""
	raw = f"{run_id}|{node_id}|{int(attempt)}".encode()
	return hashlib.sha256(raw).hexdigest()


def _ledger(data: dict) -> dict:
	ledger = data.get(LEDGER_KEY)
	if not isinstance(ledger, dict):
		ledger = {}
		data[LEDGER_KEY] = ledger
	ledger.setdefault("visits", {})
	ledger.setdefault("done", {})
	ledger.setdefault("open", {})
	return ledger


def visits(data: dict, node_id: str) -> int:
	ledger = data.get(LEDGER_KEY) if isinstance(data, dict) else None
	if not isinstance(ledger, dict):
		return 0
	return int((ledger.get("visits") or {}).get(node_id) or 0)


def key_for(run_id: str, node_id: str, data: dict, retry_attempt: int = 1) -> str:
	"""The key for the current try: past visits folded with the retry attempt (1-based)."""
	return step_key(run_id, node_id, visits(data, node_id) * VISIT_STRIDE + int(retry_attempt or 1))


def with_key(node: dict, key: str) -> dict:
	"""A copy of ``node`` carrying ``key`` for the executor."""
	return {**node, NODE_KEY: key}


def key_of(node: dict) -> str:
	return str(node.get(NODE_KEY) or "")


def replay(data: dict, key: str) -> dict | None:
	"""The recorded result when the step with ``key`` already completed, else None."""
	if not key or not isinstance(data, dict):
		return None
	ledger = data.get(LEDGER_KEY)
	if not isinstance(ledger, dict):
		return None
	done = (ledger.get("done") or {}).get(key)
	return dict(done) if isinstance(done, dict) else None


def record(data: dict, node_id: str, key: str, result: dict) -> None:
	"""Mark the step with ``key`` completed with ``result``; its visit counts at :func:`advance`."""
	if not key:
		return
	ledger = _ledger(data)
	if key in ledger["done"]:
		return
	ledger["done"][key] = result
	ledger["open"][node_id] = key


def advance(data: dict, node_id: str) -> bool:
	"""The cursor leaves ``node_id``: count its completed visit. True when the ledger changed."""
	ledger = data.get(LEDGER_KEY) if isinstance(data, dict) else None
	if not isinstance(ledger, dict) or not (ledger.get("open") or {}).pop(node_id, None):
		return False
	ledger = _ledger(data)
	ledger["visits"][node_id] = int(ledger["visits"].get(node_id) or 0) + 1
	return True
