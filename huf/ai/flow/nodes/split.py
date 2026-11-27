"""``split`` node: weighted branches plus a holdout share, bucketed deterministically per member.

Config: ``options`` (``[{label, node_id, weight}]``, weights in percent, summing to 100), ``holdout`` (percent of
members held out, 0-100, default 0) and optional ``salt`` (defaults to the flow version, CONTRACTS section 16).

Bucket: ``int.from_bytes(sha256(f"{salt}|{member_key}")[:8], "big") % 10000`` (same as the Happiol journey
runner). A member is held out when its bucket is below ``holdout * 100``. The branch is picked from a separate
bucket with salt ``f"{salt}|arm|{node_id}"``, so the holdout share and the branch split are independent.

Holdout members still walk the graph (decision 5): the split only records the run flag. It lives per run in
``context_json`` under ``_huf_split`` = ``{"holdout", "bucket", "node_id"}`` (C2), written by the first split the
run reaches and never overwritten; it is never stored in member vars, so a re-entry is bucketed afresh. The send
node suppresses marketing-class sends for held-out runs (``holdout_no_contact``); app nodes read ``ctx.holdout``.
"""

from __future__ import annotations

import hashlib

SPLIT_KEY = "_huf_split"
BUCKETS = 10000
HOLDOUT_NO_CONTACT = "holdout_no_contact"


def bucket_of(salt: str, member_key: str) -> int:
	digest = hashlib.sha256(f"{salt}|{member_key}".encode()).digest()
	return int.from_bytes(digest[:8], "big") % BUCKETS


def is_holdout(data) -> bool:
	"""Whether the run (its context data dict) was held out by a split."""
	split = data.get(SPLIT_KEY) if isinstance(data, dict) else None
	return bool(isinstance(split, dict) and split.get("holdout"))


def _number(value):
	return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def config_problems(config: dict) -> list[str]:
	"""Readable problems with a split's settings, checked on draft save and on publish."""
	problems = []
	options = config.get("options") or []
	weights = [_number((o or {}).get("weight")) if isinstance(o, dict) else None for o in options]
	if options and any(w is None or w < 0 for w in weights):
		problems.append("Every branch of a split needs a weight of 0 or more.")
	elif options and abs(sum(weights) - 100) > 1e-9:
		problems.append("The branch weights of a split must add up to 100.")
	holdout = config.get("holdout", 0)
	if _number(holdout) is None or not 0 <= holdout <= 100:
		problems.append("The holdout share of a split must be a number from 0 to 100.")
	return problems


def pick_branch(options: list, bucket: int) -> dict | None:
	"""The option whose cumulative weight range (over 0..9999) holds ``bucket``."""
	edge = 0.0
	chosen = None
	for option in options:
		weight = _number((option or {}).get("weight")) or 0
		if weight <= 0:
			continue
		edge += weight * BUCKETS / 100
		chosen = option
		if bucket < edge:
			return option
	return chosen


def exec_split(flow_run, node: dict, config: dict, settings: dict) -> dict:
	from huf.ai.flow.engine import _context_of, _persist_context

	problems = config_problems(config)
	options = [o for o in config.get("options") or [] if isinstance(o, dict) and o.get("node_id")]
	if problems or not options:
		return {
			"status": "failed",
			"error": problems[0] if problems else "Add at least one branch to this split.",
		}
	member_key = getattr(flow_run, "member_key", None)
	if not member_key:
		return {"status": "failed", "error": "A split needs the person the run is about."}

	node_id = node.get("id") or ""
	salt = str(config.get("salt") or getattr(flow_run, "flow_version", "") or "")
	bucket = bucket_of(salt, member_key)
	held_out = bucket < (config.get("holdout") or 0) * BUCKETS / 100
	option = pick_branch(options, bucket_of(f"{salt}|arm|{node_id}", member_key))
	if option is None:
		return {"status": "failed", "error": "Give at least one branch of this split a weight above 0."}

	ctx = _context_of(flow_run, settings)
	if not isinstance(ctx.data.get(SPLIT_KEY), dict):  # first split in the run wins (C2)
		ctx.data[SPLIT_KEY] = {"holdout": held_out, "bucket": bucket, "node_id": node_id}
		ctx.dirty = True
		_persist_context(flow_run, ctx, settings)
	label = option.get("label") or option["node_id"]
	return {
		"status": "success",
		"next_node_id": option["node_id"],
		"output": {"branch": label, "node_id": option["node_id"], "bucket": bucket, "holdout": held_out},
	}
