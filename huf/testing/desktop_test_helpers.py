# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Shared real-DB fixtures for the desktop workspace tool tests (not a test module)."""

import contextvars
import threading

import frappe

from huf.ai import desktop_executor as dx

FP = "0123456789abcdef"

# Lease secrets returned by ``register_desktop_executor`` (a real desktop holds this in its main
# process). The wrappers below present it the way Huf Desktop does, so tests exercise the real
# secret-gated endpoints instead of bypassing them. Pass ``lease_secret=None`` to present none.
SECRETS = {}


def secret_of(executor_id):
	return SECRETS.get(executor_id)


def register_desktop_executor(*args, **kwargs):
	"""Register through the real endpoint, remember the returned secret, and present the held
	secret on a re-register of a live lease."""
	eid = kwargs.get("executor_id")
	kwargs.setdefault("lease_secret", SECRETS.get(eid))
	out = dx.register_desktop_executor(*args, **kwargs)
	SECRETS[eid] = out["lease_secret"]
	return out


def _with_secret(endpoint):
	def call(*args, **kwargs):
		kwargs.setdefault("lease_secret", SECRETS.get(kwargs.get("executor_id")))
		return endpoint(*args, **kwargs)

	call.__name__ = endpoint.__name__
	return call


heartbeat_desktop_executor = _with_secret(dx.heartbeat_desktop_executor)
unregister_desktop_executor = _with_secret(dx.unregister_desktop_executor)
register_desktop_catalog = _with_secret(dx.register_desktop_catalog)
list_pending_desktop_tool_calls = _with_secret(dx.list_pending_desktop_tool_calls)
submit_desktop_tool_event = _with_secret(dx.submit_desktop_tool_event)


def make_user(prefix="dxtest"):
	"""Insert a real non-admin user with the Huf User role. Returns the email."""
	email = f"{prefix}-{frappe.generate_hash(length=8)}@example.com"
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": prefix,
			"send_welcome_email": 0,
			"enabled": 1,
			"roles": [{"role": "Huf User"}],
		}
	)
	user.flags.ignore_permissions = True
	user.insert()
	frappe.db.commit()
	return email


def delete_docs(pairs):
	frappe.set_user("Administrator")
	for doctype, name in pairs:
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass
	frappe.db.commit()


def make_run(user, runtime_context, resign=True, conversation=None, claim=True):
	"""Insert a real Agent Run owned by ``user`` whose runtime_context is a JSON STRING
	(as ``run_agent_sync`` stores it). Returns the run name.

	``resign`` (default) signs the desktop pin the way ``run_agent_sync`` does: AFTER the insert, bound
	to the run that now exists (its name, conversation, agent, creation and prompt). So tests that
	edit a pin dict before inserting it model a pin the server wrote. ``resign=False`` inserts it as
	given: that is how a forged pin (a Huf User writing ``runtime_context`` directly) is modelled.

	``claim`` (default) also claims a desktop-origin pin the way the worker that drains the run does
	(``claim_desktop_pin``): desktop origin is single-use, and the tool handlers only honour it in the
	job that holds the claim. ``claim=False`` leaves the pin unclaimed, i.e. a replayed run."""
	frappe.set_user(user)
	run = frappe.get_doc(
		{
			"doctype": "Agent Run",
			"status": "Started",
			"prompt": "desktop tool test",
			"runtime_context": frappe.as_json(runtime_context),
			**({"conversation": conversation} if conversation else {}),
		}
	)
	run.insert(ignore_permissions=True)
	if resign and isinstance((runtime_context or {}).get("desktop"), dict):
		runtime_context = dict(runtime_context)
		pin = dict(runtime_context["desktop"])
		pin["sig"] = dx.sign_pin(pin, run.conversation, run)
		runtime_context["desktop"] = pin
		frappe.db.set_value(
			"Agent Run", run.name, "runtime_context", frappe.as_json(runtime_context), update_modified=False
		)
	frappe.db.commit()
	if claim and resign and (runtime_context or {}).get("desktop", {}).get("origin") == "desktop":
		dx.claim_desktop_pin(run.name)
	return run.name


def desktop_pin(executor_id, user, fingerprint=FP, label="my-project", origin="desktop", conversation_id=None, **extra):
	"""A run pin signed like ``run_agent_sync`` signs it (origin and policy are trusted only when
	the signature verifies). ``extra`` keys (``agent_policy``, ``device_id``) are signed too."""
	pin = {"executor_id": executor_id, "fingerprint": fingerprint, "user": user, "label": label, "origin": origin}
	pin.update(extra)
	pin["sig"] = dx.sign_pin(pin, conversation_id)
	return {"desktop": pin}


def workspace(fingerprint=FP, mode="ask"):
	return {"label": "my-project", "fingerprint": fingerprint, "permission_mode": mode, "exec_confined": True}


def run_in_thread(fn):
	"""Run ``fn`` in a thread that shares frappe.local (same as asyncio.to_thread does).

	Returns ``(thread, errors)``; ``errors`` collects exceptions raised in the thread."""
	errors = []

	def target():
		try:
			fn()
		except BaseException as exc:  # noqa: BLE001 - reported to the test
			errors.append(exc)

	thread = threading.Thread(target=contextvars.copy_context().run, args=(target,), daemon=True)
	thread.start()
	return thread, errors
