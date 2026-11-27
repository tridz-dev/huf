"""Merge duplicate (flow, member key) rows before the unique index on Flow Member State is created.

Runs before model sync, because model sync creates the index. The latest row survives, under the
deterministic name the code looks people up by; counts, first entry, variables and history are folded in.
"""

import json

import frappe

from huf.ai.flow.runs.member import DOCTYPE, MAX_HISTORY, MAX_VARS_BYTES, member_name

TABLE = f"`tab{DOCTYPE}`"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return
	duplicates = frappe.db.sql(f"select flow, member_key from {TABLE} group by flow, member_key having count(*) > 1")
	for flow, key in duplicates:
		_merge(flow, key)


def _merge(flow: str, key: str) -> None:
	# Oldest first, so later rows win.
	rows = frappe.db.sql(
		f"select name, flow, member_key, entered_at, last_event_at, run_count, vars_json, history_json from {TABLE}"
		" where flow = %s and member_key = %s order by coalesce(last_event_at, modified), modified, name",
		(flow, key),
		as_dict=True,
	)
	latest = rows[-1]
	variables, history = {}, []
	for row in rows:
		variables.update(_load(row.vars_json, {}))
		history.extend(_load(row.history_json, []))
	encoded = json.dumps(variables)
	if len(encoded.encode("utf-8")) > MAX_VARS_BYTES:
		encoded = json.dumps(_load(latest.vars_json, {}))
	history.sort(key=lambda entry: str(entry.get("at") or ""))

	for row in rows[:-1]:
		frappe.db.sql(f"delete from {TABLE} where name = %s", row.name)
	frappe.db.sql(
		f"update {TABLE} set name = %s, run_count = %s, entered_at = %s, vars_json = %s, history_json = %s where name = %s",
		(
			member_name(latest.flow, latest.member_key),
			sum(row.run_count or 0 for row in rows),
			min((row.entered_at for row in rows if row.entered_at), default=None),
			encoded,
			json.dumps(history[-MAX_HISTORY:]),
			latest.name,
		),
	)


def _load(raw, default):
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except json.JSONDecodeError:
		return default
	return data if isinstance(data, type(default)) else default
