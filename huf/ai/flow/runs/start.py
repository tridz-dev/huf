"""Start a flow for a member, for apps. Python only, never whitelisted (CONTRACTS.md section 8).

One ``(flow, member, entry_key)`` yields one run: callers for one member are serialized by a database advisory lock,
and the run carries a hash of its entry key in its payload, which is the durable record that the entry was used.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager

import frappe

from huf.ai.flow.runs import entry, member
from huf.ai.transaction import commit_if_background

ENTRY_MARKER = "_huf_entry"
LOCK_TIMEOUT_SECONDS = 30
JOIN_ATTEMPTS = 5


def start_flow_for_member(
	flow_id: str,
	member_key: str,
	payload: dict | None,
	*,
	entry_key: str | None = None,
	trigger_node_id: str | None = None,
	run_as: str | None = None,
	enqueue: bool = True,
) -> str | None:
	"""Start a run of ``flow_id`` for ``member_key``. ``payload`` holds ids only, never PII.

	Returns the new run name, or ``None`` when nothing started: the flow is not Active, the trigger's entry policy
	skipped (or resumed a waiting run), or this ``entry_key`` (default: the member key) already started a run.
	"""
	_check_key(member_key)
	flow = frappe.db.get_value(
		"Flow Definition", flow_id, ["status", "owner", "definition_json"], as_dict=True
	)
	if not flow or flow.status != "Active":
		return None
	node = _trigger_node(flow.definition_json, trigger_node_id)
	user = flow.owner if run_as is None else run_as
	if user == "Guest" or not frappe.db.exists("User", user):
		raise ValueError("A flow cannot run as Guest or as a user that does not exist.")

	with _session(user):
		run = _create_run(flow_id, member_key, dict(payload or {}), entry_key, node)
		if not run:
			return None
		if enqueue:
			frappe.enqueue(
				"huf.ai.flow.engine.run_flow",
				queue="default",
				flow_run_name=run,
				# in a request the worker must not look for the run before Frappe commits it
				enqueue_after_commit=bool(getattr(frappe.local, "request", None)),
			)
		else:
			from huf.ai.flow import engine

			engine.run_flow(run)
	return run


def _check_key(member_key) -> None:
	if (
		not isinstance(member_key, str)
		or not member_key
		or member_key != member_key.strip()
		or len(member_key) > member.MAX_KEY_CHARS
	):
		raise ValueError(
			f"member_key must be 1 to {member.MAX_KEY_CHARS} characters without surrounding spaces."
		)


def _trigger_node(definition_json, trigger_node_id: str | None) -> dict:
	from huf.ai.flow.triggers import parse_definition

	defn = parse_definition(definition_json)
	entries = defn.get("entry")
	entries = set(entries) if isinstance(entries, list) else {entries}
	nodes = [
		n
		for n in defn.get("nodes", []) or []
		if isinstance(n, dict) and n.get("id") in entries and str(n.get("type") or "").startswith("trigger.")
	]
	if trigger_node_id is not None:
		nodes = [n for n in nodes if n.get("id") == trigger_node_id]
	if len(nodes) != 1:
		raise ValueError("Name one trigger step of this flow in trigger_node_id.")
	return nodes[0]


def _create_run(
	flow_id: str, member_key: str, payload: dict, entry_key: str | None, node: dict
) -> str | None:
	"""The new run's name, or ``None`` when this entry is a duplicate or the entry policy starts nothing."""
	from huf.ai.flow import engine

	key = _join_member(flow_id, member_key)
	if not key:
		return None
	with _member_lock(flow_id, key):
		marker = hashlib.sha256(f"{flow_id}\0{key if entry_key is None else entry_key}".encode()).hexdigest()
		# Outside a request, commit for a fresh snapshot; in one, a locking read sees what was committed since.
		commit_if_background()
		if frappe.db.get_value(
			"Agent Flow Run",
			{"flow_id": flow_id, "member_key": key, "trigger_payload": ["like", f"%{marker}%"]},
			"name",
			for_update=bool(getattr(frappe.local, "request", None)),
		):
			return None
		policy = entry.entry_policy_of(node.get("config"))
		if entry.entry_decision(flow_id, policy, key, payload)["action"] != "start":
			return None
		# Other trigger types would derive a member from the session or the payload; the app's key is passed instead.
		trigger_type = {
			"trigger.webhook": "Webhook",
			"trigger.schedule": "Schedule",
			"trigger.doc-event": "Doc Event",
			"trigger.app": "App",
		}.get(node.get("type"), "Manual")
		run = engine.create_flow_run(
			flow_id=flow_id,
			payload=payload,
			entry_marker=marker,
			trigger_type=trigger_type,
			ignore_permissions=True,
			member_key=key,
		)
		if run.current_node_id != node["id"]:
			run.db_set("current_node_id", node["id"])
		commit_if_background()
	return run.name


def _join_member(flow_id: str, member_key: str) -> str | None:
	"""Insert-or-skip the member and return the key as stored.

	The unique ``(flow, member_key)`` index ignores case while the row name hashes it, so a key that differs only in
	case belongs to the existing member and must be used with its stored spelling.
	"""
	in_request = bool(getattr(frappe.local, "request", None))
	filters = {"flow": flow_id, "member_key": member_key}
	for attempt in range(JOIN_ATTEMPTS):
		commit_if_background()  # a fresh snapshot; also the lock must come first, see member.claim_entry
		key = frappe.db.get_value(member.DOCTYPE, filters, "member_key")
		if key:
			return key  # no write for a known member: concurrent upserts under two spellings can deadlock
		try:
			member.lock_member(flow_id, member_key)
			# in a request the snapshot may predate a row another caller committed: read it with a lock
			key = frappe.db.get_value(member.DOCTYPE, filters, "member_key", for_update=in_request)
			commit_if_background()
			return key
		except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
			pass  # created meanwhile under another spelling: read it on the next attempt
		except frappe.QueryDeadlockError:
			if in_request or attempt == JOIN_ATTEMPTS - 1:
				raise  # the caller's transaction is gone, it cannot be retried here
			frappe.db.rollback()
	return None


@contextmanager
def _member_lock(flow_id: str, key: str):
	"""A session advisory lock: unlike a row lock it survives the commits made while the run is created.

	In a request nothing is committed here, so the lock is released only once the transaction ends.
	"""
	name = "huf_entry:" + hashlib.sha256(f"{flow_id}\0{key}".encode()).hexdigest()[:40]
	got = frappe.db.multisql(
		{
			"mariadb": "select get_lock(%s, %s)",
			"postgres": "select 1 from (select pg_advisory_lock(hashtext(%s)), %s) as held",
		},
		(name, LOCK_TIMEOUT_SECONDS),
	)
	if not got or got[0][0] != 1:
		raise frappe.QueryTimeoutError("Another entry of this member is still being created. Try again.")

	def release():
		frappe.db.multisql(
			{"mariadb": "select release_lock(%s)", "postgres": "select pg_advisory_unlock(hashtext(%s))"},
			(name,),
		)

	if not getattr(frappe.local, "request", None):
		try:
			yield
		finally:
			release()
		return
	frappe.db.after_commit.add(release)
	frappe.db.after_rollback.add(release)
	yield


@contextmanager
def _session(user: str):
	"""Run as ``user`` and give the caller its session back (``set_user`` also resets sid, data and form_dict)."""
	session = frappe.local.session
	before = (session.user, session.sid, session.data)
	form_dict = frappe.local.form_dict
	origin = frappe.flags.huf_flow_run_origin
	changed = user != before[0]
	try:
		if changed:
			frappe.set_user(user)
		frappe.flags.huf_flow_run_origin = True  # docs written by this run must not re-trigger flows
		yield
	finally:
		frappe.flags.huf_flow_run_origin = origin
		if changed:
			frappe.set_user(before[0])
			frappe.local.session.sid, frappe.local.session.data = before[1], before[2]
			frappe.local.form_dict = form_dict
