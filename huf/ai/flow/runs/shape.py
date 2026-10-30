# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Extra fields on the Flow Run payloads that the run story needs (UX-4).

``get_flow_run`` and the run lists add: who started the run, its number within its flow, a short hint of the
data it started with, the business outcome (Approved / Rejected / Timed out, or the End step's own outcome),
and a ``step_meta`` map (type, loop body) so the page can tell the story of the steps in plain words.

The pure helpers (``step_meta_from``, ``compute_outcome``, ``input_hint``) need no site; the ``extras_*``
functions read the flow definition and users.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_right

import frappe

# Step title shown when a saved step has no title of its own (flows written outside the editor).
_STEP_TYPE_TITLES = {
	"agent.run": "Run agent",
	"tool.call": "Call tool",
	"router.llm": "LLM Router",
	"condition": "Condition (If/Else)",
	"foreach": "Loop",
	"human.approval": "Human in Loop",
	"end": "End",
	"transform": "Transform data",
	"code.run": "Execute code",
}

from huf.ai.flow.runs.outcome import stored_outcome

_DECISION_OUTCOMES = {
	"approved": ("Approved", "good"),
	"rejected": ("Rejected", "bad"),
	"timeout": ("Timed out", "neutral"),
}
_TONES = {"good", "neutral", "bad"}
_SECRET_WORDS = ("secret", "token", "password", "passwd", "api_key", "apikey", "authorization", "credential")
# Facts the engine adds on its own (schedule runs): not something the person sent, and not worth a hint.
_INTERNAL_WORDS = ("node", "scheduled", "trigger", "cron")
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")
NODE_OUTPUTS_KEY = "__node_outputs__"
HINT_MAX_CHARS = 70
HINT_MAX_FACTS = 2


def _nodes_of(defn) -> list:
	"""The node list of a saved or pinned definition (a pinned one wraps the graph)."""
	if isinstance(defn, dict) and isinstance(defn.get("graph"), dict):
		defn = defn["graph"]
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	return [n for n in (nodes or []) if isinstance(n, dict) and n.get("id")]


def _clean_outcome(raw) -> dict | None:
	"""An End step's own ``outcome`` ``{label, tone}``; a missing or odd tone reads as neutral."""
	if not isinstance(raw, dict) or not str(raw.get("label") or "").strip():
		return None
	tone = str(raw.get("tone") or "").lower()
	return {"label": str(raw["label"]).strip(), "tone": tone if tone in _TONES else "neutral"}


def step_meta_from(defn) -> dict:
	"""``{node_id: {type, body?, outcome?}}`` for every step of a definition."""
	meta: dict = {}
	for n in _nodes_of(defn):
		cfg = n.get("config") if isinstance(n.get("config"), dict) else {}
		entry: dict = {"type": n.get("type") or ""}
		if n.get("type") == "foreach":
			entry["body"] = [b for b in (cfg.get("body") or []) if isinstance(b, str)]
		if n.get("type") == "output":
			outcome = _clean_outcome(cfg.get("outcome"))
			if outcome:
				entry["outcome"] = outcome
		meta[n["id"]] = entry
	return meta


def _decision_outputs(outputs: dict) -> list:
	return [v for v in outputs.values() if isinstance(v, dict) and v.get("decision") in _DECISION_OUTCOMES]


def compute_outcome(status: str | None, current_node_id: str | None, ctx: dict, meta: dict) -> dict | None:
	"""The business result of a finished run, or None when the run just finished.

	An End step with its own outcome wins. Otherwise a run that went through an approval reads as what the
	approver decided, so a rejected order never looks like plain success.
	"""
	if status != "Success":
		return None
	own = (meta.get(current_node_id) or {}).get("outcome")
	if own:
		return own
	outputs = ctx.get(NODE_OUTPUTS_KEY) if isinstance(ctx, dict) else None
	decisions = _decision_outputs(outputs) if isinstance(outputs, dict) else []
	if not decisions:
		return None
	label, tone = _DECISION_OUTCOMES[decisions[-1]["decision"]]
	return {"label": label, "tone": tone}


def _fact_label(key: str) -> str:
	return key.replace("_", " ").replace("-", " ").strip().lower()


def _plain_text(value: str) -> str:
	"""A rich-text value as plain words: tags removed, entities decoded, whitespace collapsed."""
	if "<" not in value and "&" not in value:
		return value.strip()
	import html as _html
	return " ".join(_html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def input_hint(ctx: dict) -> str:
	"""A few facts from the data a run started with ("amount 150, note walkthrough B"); empty when there are none."""
	if not isinstance(ctx, dict):
		return ""
	facts = []
	for key, value in ctx.items():
		if key.startswith("__") or any(w in key.lower() for w in _SECRET_WORDS + _INTERNAL_WORDS):
			continue
		if isinstance(value, str):
			value = _plain_text(value)
		if isinstance(value, str) and _DATE_LIKE.match(value.strip()):
			continue
		if isinstance(value, bool):
			value = "yes" if value else "no"
		if isinstance(value, (str, int, float)) and str(value).strip():
			facts.append(f"{_fact_label(key)} {str(value).strip()}")
		if len(facts) >= HINT_MAX_FACTS:
			break
	hint = ", ".join(facts)
	return hint if len(hint) <= HINT_MAX_CHARS else hint[: HINT_MAX_CHARS - 1].rstrip() + "…"


def _load_json(raw):
	try:
		return json.loads(raw) if isinstance(raw, str) else (raw or {})
	except (json.JSONDecodeError, TypeError):
		return {}


def _full_name(user: str | None) -> str | None:
	return (frappe.db.get_value("User", user, "full_name") or user) if user else None


def run_number(flow_id: str, creation) -> int:
	"""1-based place of a run among all runs of its flow, oldest first."""
	return frappe.db.count("Flow Run", {"flow_id": flow_id, "creation": ["<=", creation]})


def extras_for_detail(doc, ctx: dict) -> dict:
	"""Fields added to ``get_flow_run``."""
	defn = _load_json(doc.pinned_definition) if doc.pinned_definition else _load_json(
		frappe.db.get_value("Flow Definition", doc.flow_id, "definition_json") if doc.flow_id else None
	)
	meta = step_meta_from(defn)
	return {
		"step_meta": meta,
		"outcome": (stored_outcome(doc) if doc.status == "Success" else None) or compute_outcome(doc.status, doc.current_node_id, ctx, meta),
		"started_by": doc.owner,
		"started_by_name": _full_name(doc.owner),
		"run_number": run_number(doc.flow_id, doc.creation),
		"modified_at": _modified_iso(doc.modified),
	}


def _modified_iso(value):
	from huf.ai.flow.api import _utc_iso

	return _utc_iso(value)


def shape_list_rows(rows: list, names: dict, can_fail: bool) -> list:
	"""Fill a list of Flow Run rows (fetched with ``LIST_EXTRA_FIELDS``) with the fields the history shows."""
	from huf.ai.flow.api import _is_stale, _utc_iso

	by_flow: dict = {}
	metas: dict = {}
	people: dict = {}
	for r in rows:
		if r.flow_id not in by_flow:
			created = frappe.get_all(
				"Flow Run", filters={"flow_id": r.flow_id}, pluck="creation", order_by="creation asc", limit_page_length=0
			)
			by_flow[r.flow_id] = created
			raw = frappe.db.get_value("Flow Definition", r.flow_id, "definition_json") if r.flow_id else None
			metas[r.flow_id] = step_meta_from(_load_json(raw))
		if r.owner not in people:
			people[r.owner] = _full_name(r.owner)
	for r in rows:
		ctx = _load_json(r.pop("context_json", None))
		creation = r.pop("creation", None)
		r["flow_name"] = names.get(r.flow_id) or r.flow_id
		r["stale"] = _is_stale(r.status, r.modified)
		r["can_mark_failed"] = r["stale"] and can_fail
		r["started_at"] = _utc_iso(r.started_at)
		r["completed_at"] = _utc_iso(r.completed_at)
		r["modified"] = _utc_iso(r.modified)
		r["started_by"] = r.pop("owner", None)
		r["started_by_name"] = people.get(r["started_by"])
		r["run_number"] = bisect_right(by_flow[r.flow_id], creation) if creation is not None else None
		r["input_hint"] = input_hint(ctx)
		recorded = stored_outcome(r) if r.status == "Success" else None
		r["outcome"] = recorded or compute_outcome(r.status, r.current_node_id, ctx, metas.get(r.flow_id, {}))
		r.pop("outcome_label", None)
		r.pop("outcome_tone", None)
	return rows
