"""App-scoped run summary across one app's flows (D-END-TO-END, H-W7-12).

A host app (Happiol) shows a programme-wide view of its runs without sending its users to ``/huf``. Both APIs are
scoped to the flows whose ``owner_app`` is ``app`` and that the caller may ``view`` (``flow_access``). They return
ids (including the node the run is at), status, the final reason code, timestamps and a masked member key: never step outputs, context or payloads.

The caller's User Permissions and the app's ``huf_flow_app_narrow`` hook apply to both.

Runs are filtered on ``(owner_app, status, modified)``; the index is added in ``agent_flow_run.on_doctype_update``.
"""

from __future__ import annotations

import json

import frappe
from frappe.core.doctype.user_permission.user_permission import get_user_permissions
from frappe.utils import cint, get_datetime

from huf.ai.api_support import require_permission
from huf.ai.flow.app_scope.access import apps_for, flow_access, is_privileged
from huf.ai.flow.app_scope.api_guards import guard_app_named
from huf.ai.flow.runs.access import get_user_permitted_runs

DOCTYPE = "Agent Flow Run"
NODE_OUTPUTS_KEY = "__node_outputs__"
MAX_LIMIT = 500
GROUP_FIELDS = ("flow", "status", "reason", "node")
# group key -> run column (``reason`` is derived from the context, so it has none) and -> ``_row`` key
GROUP_COLUMNS = {"flow": "flow_definition", "status": "status", "node": "current_node_id"}
ROW_KEYS = {"flow": "flow_id", "node": "end_node"}
MASK_PREFIX = "****"
MASK_KEEP = 4


def _require_app_view(app) -> None:
	"""``guard_app_named`` plus its rule stated as an explicit permission check (an empty ``app`` is left to the guard)."""
	guard_app_named(app)
	require_permission(is_privileged() or not app or app in apps_for(None, "view"), "Not permitted")


@frappe.whitelist()
def list_app_runs(app, status=None, flow_ids=None, member_key=None, since=None, limit=100) -> list[dict]:
	"""Newest first, at most ``limit`` (capped at 500) runs of ``app``'s flows the caller may view."""
	_require_app_view(app)
	limit = max(1, min(cint(limit) or 100, MAX_LIMIT))
	rows = _runs(app, status, flow_ids, member_key, since, limit=limit)
	return [_row(r) for r in rows]


@frappe.whitelist()
def count_app_runs(
	app, group_by="flow,status,reason", status=None, flow_ids=None, since=None, include_test=0
) -> list[dict]:
	"""Run counts of ``app``'s viewable flows grouped by any of ``flow``, ``status``, ``reason``, ``node``.

	Test runs are left out unless ``include_test`` is set; a run with no ``run_mode`` counts.
	"""
	_require_app_view(app)
	keys = [k.strip() for k in str(group_by or "").split(",") if k.strip()]
	if not keys or any(k not in GROUP_FIELDS for k in keys):
		frappe.throw(frappe._("group_by takes flow, status, reason and node"), frappe.ValidationError)
	flows = _viewable_flows(app, flow_ids)
	if not flows:
		return []
	exclude_test = not cint(include_test)
	if "reason" not in keys:
		return _sql_counts(app, flows, keys, status, since, exclude_test)
	# ``node`` is free text that SQL groups without regard to case, and User Permissions are checked run by run:
	# both read every run instead of correcting SQL totals.
	if "node" in keys or get_user_permissions(frappe.session.user):
		counts = _row_reason_counts(app, flows, keys, status, since, exclude_test)
	else:
		counts = _narrow_reason_counts(app, flows, keys, status, since, exclude_test)
	return [{**dict(zip(keys, key, strict=True)), "count": n} for key, n in sorted(counts.items(), key=str)]


# --- query --------------------------------------------------------------------------------------------------


def _as_list(value) -> list[str] | None:
	if value in (None, "", []):
		return None
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			value = value.split(",")
	if isinstance(value, str):
		value = [value]
	return [str(v).strip() for v in value if str(v).strip()]


def _viewable_flows(app: str, flow_ids=None) -> list[str]:
	wanted = _as_list(flow_ids)
	filters = {"owner_app": app}
	if wanted is not None:
		filters["name"] = ("in", wanted)
	names = frappe.get_all("Flow Definition", filters=filters, pluck="name", ignore_permissions=True)
	user = frappe.session.user
	return sorted(n for n in names if flow_access(user, n, "view"))


def _filters(app, flows, status, member_key, since, exclude_test=False) -> dict:
	filters = {"owner_app": app, "flow_definition": ("in", flows)}
	statuses = _as_list(status)
	if statuses:
		filters["status"] = ("in", statuses)
	if since:
		filters["modified"] = (">=", get_datetime(since))
	if member_key:
		filters["member_key"] = str(member_key)
	if exclude_test:
		filters["run_mode"] = ("!=", "Test")
	return filters


def _runs(app, status, flow_ids, member_key, since, *, limit, exclude_test=False):
	flows = _viewable_flows(app, flow_ids)
	if not flows:
		return []
	return get_user_permitted_runs(
		DOCTYPE,
		filters=_filters(app, flows, status, member_key, since, exclude_test),
		fields=[
			"name", "flow_definition", "flow_version", "status", "run_mode", "member_key",
			"current_node_id", "context_json", "started_at", "completed_at", "creation", "modified",
		],
		order_by="modified desc",
		limit_page_length=limit or 0,
		ignore_permissions=True,
	)  # fmt: skip


def _sql_counts(app, flows, keys, status, since, exclude_test) -> list[dict]:
	group = [GROUP_COLUMNS[k] for k in keys]
	columns = [c if c == k else f"{c} as {k}" for k, c in zip(keys, group, strict=True)]
	return get_user_permitted_runs(
		DOCTYPE,
		filters=_filters(app, flows, status, None, since, exclude_test),
		fields=[*columns, {"COUNT": "name", "as": "count"}],
		group_by=", ".join(group),
		order_by=", ".join(group),
		ignore_permissions=True,
	)


def _row_reason_counts(app, flows, keys, status, since, exclude_test) -> dict[tuple, int]:
	counts: dict[tuple, int] = {}
	for r in _runs(app, status, flows, None, since, limit=None, exclude_test=exclude_test):
		row = _row(r)
		key = tuple(row[ROW_KEYS.get(k, k)] for k in keys)
		counts[key] = counts.get(key, 0) + 1
	return counts


def _narrow_reason_counts(app, flows, keys, status, since, exclude_test) -> dict[tuple, int]:
	"""Totals from SQL, then only the contexts that mention ``reason_code`` are read and moved to their reason.

	A run whose context text has no ``reason_code`` cannot have a reason (the JSON writers never escape the key).
	Both queries run in one transaction, so they see the same runs.
	"""
	plain = [k for k in keys if k != "reason"]

	def key_of(values, reason) -> tuple:
		return tuple(reason if k == "reason" else values[k] for k in keys)

	if plain:
		totals = _sql_counts(app, flows, plain, status, since, exclude_test)
	else:
		# not ``db.count``: it skips ``get_all``'s IFNULL on ``run_mode != 'Test'`` and loses runs with none
		totals = get_user_permitted_runs(
			DOCTYPE,
			filters=_filters(app, flows, status, None, since, exclude_test),
			fields=[{"COUNT": "name", "as": "count"}],
			order_by=None,
			ignore_permissions=True,
		)
	counts = {key_of(t, None): t["count"] for t in totals}
	candidates = get_user_permitted_runs(
		DOCTYPE,
		filters={
			**_filters(app, flows, status, None, since, exclude_test),
			"context_json": ("like", "%reason_code%"),
		},
		fields=[*(f"{GROUP_COLUMNS[k]} as {k}" for k in plain), "context_json"],
		order_by=None,
		ignore_permissions=True,
	)
	for r in candidates:
		reason = final_reason(r.context_json)
		if reason is None:
			continue
		counts[key_of(r, None)] -= 1
		key = key_of(r, reason)
		counts[key] = counts.get(key, 0) + 1
	return {key: n for key, n in counts.items() if n}


# --- shaping ------------------------------------------------------------------------------------------------


def final_reason(context_json) -> str | None:
	"""The reason code of the last step that recorded one, or None. Only the code leaves this function."""
	from huf.ai.flow.support import reason_codes

	try:
		ctx = json.loads(context_json) if isinstance(context_json, str) else context_json
	except ValueError:
		return None
	outputs = ctx.get(NODE_OUTPUTS_KEY) if isinstance(ctx, dict) else None
	if not isinstance(outputs, dict):
		return None
	for output in reversed(list(outputs.values())):
		if isinstance(output, dict) and output.get("reason_code"):
			return reason_codes.normalize(output["reason_code"])
	return None


def mask_member(member_key) -> str | None:
	key = str(member_key or "")
	if not key:
		return None
	return MASK_PREFIX + key[-MASK_KEEP:] if len(key) > MASK_KEEP * 2 else MASK_PREFIX


def _iso(value):
	return value.isoformat() if hasattr(value, "isoformat") else value


def _row(r) -> dict:
	return {
		"run_id": r.name,
		"flow_id": r.flow_definition,
		"flow_version": r.flow_version,
		"status": r.status,
		"run_mode": r.run_mode,
		"reason": final_reason(r.context_json),
		"end_node": r.current_node_id,
		"member": mask_member(r.member_key),
		"started_at": _iso(r.started_at),
		"completed_at": _iso(r.completed_at),
		"created_at": _iso(r.creation),
		"modified_at": _iso(r.modified),
	}
