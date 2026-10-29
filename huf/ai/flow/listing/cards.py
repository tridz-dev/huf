# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""What the Flows list shows on each card, in one request (UX-11).

The list used to load every flow's full definition one by one just to count its steps. This returns, for a page of
flows, the plain facts a card needs: what starts the flow, the order of its steps (for the icon strip), how many
steps it has, and how the last run went. Search covers name, description and category; the sort is chosen by the
caller. Nothing secret leaves here: the webhook secret is never read into the answer.

Run the tests with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux11_cards
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.api_support import require_permission

MAX_PAGE = 100
MAX_STEPS_SHOWN = 12

_SORTS = {
	"recent": "modified desc",
	"name": "flow_name asc",
	"oldest": "modified asc",
}

_TRIGGER_KEYS = {
	"trigger.webhook": ("method",),
	"trigger.schedule": ("cron",),
	"trigger.doc-event": ("doctype", "event"),
}


def _parse(raw) -> dict:
	try:
		data = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except (TypeError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}


def _links(node: dict) -> list[str]:
	"""Ids a step leads to, in reading order: its next step, then the branches it carries in its own config."""
	config = node.get("config") if isinstance(node.get("config"), dict) else {}
	found: list[str] = []

	def add(value):
		if isinstance(value, str) and value:
			found.append(value)

	add(node.get("next"))
	for key in ("on_true", "on_false", "approve_next", "reject_next", "timeout_next", "default"):
		add(config.get(key))
	for option in config.get("options") or []:
		if isinstance(option, dict):
			add(option.get("node_id"))
	for body_id in config.get("body") or []:
		add(body_id)
	add(node.get("on_error"))
	return found


def summarize_definition(defn: dict) -> dict:
	"""``{trigger, steps, step_count}`` for a flow graph. Steps are in the order a person reads the flow."""
	nodes = defn.get("nodes") if isinstance(defn.get("nodes"), list) else []
	by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}

	entry = defn.get("entry")
	entry_ids = [entry] if isinstance(entry, str) else [e for e in (entry or []) if isinstance(e, str)]
	trigger_node = next((by_id[e] for e in entry_ids if e in by_id and str(by_id[e].get("type", "")).startswith("trigger.")), None)
	if trigger_node is None:
		trigger_node = next((n for n in by_id.values() if str(n.get("type", "")).startswith("trigger.")), None)

	trigger = {"type": "unset"}
	if trigger_node is not None and trigger_node.get("type") != "trigger.unset":
		config = trigger_node.get("config") if isinstance(trigger_node.get("config"), dict) else {}
		trigger = {"type": str(trigger_node["type"]).split(".", 1)[1]}
		for key in _TRIGGER_KEYS.get(trigger_node["type"], ()):
			if isinstance(config.get(key), str):
				trigger[key] = config[key]

	order: list[str] = []
	seen: set[str] = set()
	queue = [e for e in entry_ids if e in by_id]
	while queue:
		current = queue.pop(0)
		if current in seen:
			continue
		seen.add(current)
		order.append(current)
		queue.extend(link for link in _links(by_id[current]) if link in by_id and link not in seen)
	order.extend(i for i in by_id if i not in seen)

	steps = []
	for node_id in order:
		node = by_id[node_id]
		node_type = str(node.get("type", ""))
		if node_type.startswith("trigger."):
			continue
		config = node.get("config") if isinstance(node.get("config"), dict) else {}
		step = {"type": node_type}
		if node_type == "tool.call" and isinstance(config.get("tool_id"), str):
			step["tool_id"] = config["tool_id"]
		steps.append(step)
	return {"trigger": trigger, "steps": steps[:MAX_STEPS_SHOWN], "step_count": len(steps)}


def _last_runs(flow_ids: list[str], labels: dict[str, dict]) -> dict[str, dict]:
	"""The most recent run of each flow. Empty when the person may not read runs."""
	if not flow_ids or not frappe.has_permission("Flow Run", "read"):
		return {}
	from huf.ai.flow.api import _is_stale, _utc_iso

	rows = frappe.db.sql(
		"""
		select r.flow_id, r.status, r.started_at, r.completed_at, r.modified, r.current_node_id
		from `tabFlow Run` r
		inner join (
			select flow_id, max(creation) as latest from `tabFlow Run` where flow_id in %(ids)s group by flow_id
		) m on m.flow_id = r.flow_id and m.latest = r.creation
		""",
		{"ids": tuple(flow_ids)},
		as_dict=True,
	)
	out: dict[str, dict] = {}
	for row in rows:
		run = {
			"status": row.status,
			"stale": _is_stale(row.status, row.modified),
			"at": _utc_iso(row.completed_at or row.started_at or row.modified),
		}
		if row.status == "Failed" and row.current_node_id:
			title = (labels.get(row.flow_id) or {}).get(row.current_node_id)
			if title:
				run["failed_step"] = title
		out[row.flow_id] = run
	return out


@frappe.whitelist()
def list_flow_cards(
	search: str | None = None,
	status: str | None = None,
	category: str | None = None,
	sort: str = "recent",
	limit: int = MAX_PAGE,
	start: int = 0,
) -> dict:
	"""A page of flows with what a list card needs: ``{items, total}``.

	``search`` matches the name, the description and the category (case does not matter). ``status`` is Draft, Active
	or Archived; ``category`` is a category name (or ``Uncategorized`` for flows without one). Only flows the caller may
	read are returned.
	"""
	require_permission(frappe.has_permission("Flow Definition", "read"), "Not permitted")

	limit = max(1, min(int(limit or MAX_PAGE), MAX_PAGE))
	start = max(0, int(start or 0))
	order_by = _SORTS.get(sort or "recent", _SORTS["recent"])

	filters: list = []
	if status in ("Draft", "Active", "Archived"):
		filters.append(["status", "=", status])
	if category and category.lower() != "all":
		if category.lower() == "uncategorized":
			filters.append(["category", "in", ["", None]])
		else:
			filters.append(["category", "like", category])

	or_filters = None
	text = (search or "").strip()
	if text:
		like = f"%{text}%"
		or_filters = [["flow_name", "like", like], ["description", "like", like], ["category", "like", like]]

	total = len(
		frappe.get_list("Flow Definition", filters=filters, or_filters=or_filters, pluck="name", limit_page_length=0)
	)
	rows = frappe.get_list(
		"Flow Definition",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "flow_id", "flow_name", "description", "category", "status", "modified"],
		order_by=order_by,
		limit_start=start,
		limit_page_length=limit,
	)

	# get_list already limited the rows to ones the caller may read; the graph is read only to derive the summary.
	graphs = {
		r.name: _parse(r.definition_json)
		for r in frappe.get_all(
			"Flow Definition",
			filters={"name": ["in", [row.name for row in rows]]} if rows else {"name": ""},
			fields=["name", "definition_json"],
		)
	}
	labels = {
		row.flow_id: {
			n["id"]: n.get("_label")
			for n in (graphs.get(row.name, {}).get("nodes") or [])
			if isinstance(n, dict) and isinstance(n.get("id"), str) and isinstance(n.get("_label"), str)
		}
		for row in rows
	}
	runs = _last_runs([row.flow_id for row in rows], labels)

	from huf.ai.flow.api import _utc_iso

	items = []
	for row in rows:
		summary = summarize_definition(graphs.get(row.name, {}))
		items.append(
			{
				"flow_id": row.flow_id,
				"flow_name": row.flow_name or row.flow_id,
				"description": row.description or "",
				"category": row.category or "",
				"status": row.status,
				"modified": _utc_iso(row.modified),
				"last_run": runs.get(row.flow_id),
				**summary,
			}
		)
	return {"items": items, "total": total}


def category_names() -> list[str]:
	"""Distinct categories in use, for the filter and the category picker."""
	require_permission(frappe.has_permission("Flow Definition", "read"), _("Not permitted"))
	rows = frappe.get_list("Flow Definition", fields=["category"], filters=[["category", "!=", ""]], distinct=True, limit_page_length=0)
	return sorted({r.category for r in rows if r.category})


@frappe.whitelist()
def list_flow_categories() -> list[str]:
	"""Categories that flows use, sorted. Feeds the list filter and the settings picker."""
	return category_names()
