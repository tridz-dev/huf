# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Send-time member recipient (H-W2-26): the run's member is resolved to a phone number at send time only.

A send step names the member as its recipient with the sentinel ``recipient: "$member"``. An app registers
providers in ``hooks.py``::

        huf_send_recipient_providers = ["my_app.sending.recipient"]

A provider is called as ``provider(gateway, member_keys, context)`` and answers ``{member_key: str}``,
leaving out members it cannot reach. Providers run in hook order and the first str for a member wins. A
member still missing, a value that is not a str, a provider that raises or answers in another shape, and a
broken hook lookup all block with ``recipient_unbound`` (fail closed, final).

The number lives only in the returned value, which goes to the guard chain and the transport. This module
writes nothing; its error carries the code only and its log line the hook path and exception class. The
run, step output, outbox row (``recipient_ref = "$member"``) and trace never hold it (G4).
"""

import frappe

HOOK = "huf_send_recipient_providers"
MEMBER = "$member"
RECIPIENT_UNBOUND = "recipient_unbound"
CONTEXT_KEYS = ("flow_id", "flow_version", "run_id", "node_id")


class RecipientUnbound(Exception):
	"""The send is blocked: the member has no recipient."""

	code = RECIPIENT_UNBOUND

	def __init__(self):
		super().__init__(RECIPIENT_UNBOUND)


def is_member_ref(ref) -> bool:
	"""Whether a step's ``recipient`` is the run's member sentinel."""
	return isinstance(ref, str) and ref.strip() == MEMBER


def resolve(gateway: str, member_key: str | None, ctx: dict) -> str:
	"""The recipient of ``member_key``, or raise :class:`RecipientUnbound`."""
	if not member_key:
		raise RecipientUnbound()
	value = resolve_batch(gateway, [member_key], ctx).get(member_key)
	if not isinstance(value, str):
		raise RecipientUnbound()
	return value


def resolve_batch(gateway: str, member_keys: list[str], ctx: dict) -> dict:
	"""``{member_key: str | RecipientUnbound}`` with one call per provider. Never raises for a block."""
	members = [m for m in dict.fromkeys(member_keys) if m]
	if not members:
		return {}
	context = {key: ctx.get(key) for key in CONTEXT_KEYS}
	found = _collect(gateway, members, context)
	if found is None:
		return {member: RecipientUnbound() for member in members}
	return {member: found.get(member) or RecipientUnbound() for member in members}


def _collect(gateway: str, members: list[str], context: dict) -> dict | None:
	"""First non-empty str per member across the providers; None when any of them fails or none is registered."""
	found: dict = {}
	path = None
	try:
		paths = frappe.get_hooks(HOOK) or []
		paths = [paths] if isinstance(paths, str) else list(paths)
		if not paths:
			return None
		for path in paths:
			answer = frappe.get_attr(path)(gateway, list(members), dict(context))
			if not isinstance(answer, dict):
				_warn(path, "invalid result")
				return None
			for member in members:
				if member in answer and member not in found:
					value = answer[member]
					if not isinstance(value, str):
						_warn(path, "invalid result")
						return None
					if value.strip():
						found[member] = value.strip()
	except Exception as error:  # noqa: BLE001 - fail closed; the message may hold a number
		_warn(path, type(error).__name__)
		return None
	return found


def _warn(path: str | None, what: str) -> None:
	try:
		frappe.logger("flow").warning(f"send recipient provider {path} blocked: {what}")
	except Exception:  # noqa: BLE001, S110 - logging must never turn a block into another error
		pass
