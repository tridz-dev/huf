# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Send-time token binder (H-W2-24): values are read at send time and never stored.

An app registers providers in ``hooks.py``::

	huf_send_token_providers = ["my_app.sending.tokens"]

A provider is called as ``provider(template_ref, token_names, member_keys, context)`` and answers
``{member_key: {token: str}}``, leaving out what it does not know. Providers run in hook order and the first
value for a token wins. A token that is still missing or is not a str, a provider that raises or answers in
another shape, and a broken hook lookup all block with ``token_unbound``.

Values live only in the returned dict, which goes to the transport and nowhere else. This module writes
nothing; its error carries token names and the code, and its log line the hook path and exception class.
It raises only from frames that hold no value, so a traceback dumped with locals cannot leak one.
"""

import frappe

HOOK = "huf_send_token_providers"
TOKEN_UNBOUND = "token_unbound"
CONTEXT_KEYS = ("flow_id", "flow_version", "run_id", "node_id")


class TokenUnbound(Exception):  # noqa: N818 - name fixed by CONTRACTS.md section 7
	"""The send is blocked: ``token_names`` could not be bound."""

	code = TOKEN_UNBOUND

	def __init__(self, token_names: list[str]):
		self.token_names = list(token_names)
		super().__init__(f"{TOKEN_UNBOUND}: {', '.join(self.token_names)}")


def bind(template_ref: str, token_names: list[str], member_key: str, ctx: dict) -> dict:
	"""``{token: value}`` for one send, or raise :class:`TokenUnbound`."""
	result = bind_batch(template_ref, token_names, [member_key], ctx)[member_key]
	if isinstance(result, TokenUnbound):
		raise result
	return result


def bind_batch(template_ref: str, token_names: list[str], member_keys: list[str], ctx: dict) -> dict:
	"""Bind a send batch with one call per provider. Never raises for a block.

	Returns ``{member_key: {token: value} | TokenUnbound}``. Leave ``run_id`` out of ``ctx`` when the batch
	spans runs.
	"""
	names = list(dict.fromkeys(token_names))
	members = list(dict.fromkeys(member_keys))
	if not names or not members:
		return {member: {} for member in members}

	context = {key: ctx.get(key) for key in CONTEXT_KEYS}
	found = _collect(template_ref, names, members, context)
	if found is None:
		return {member: TokenUnbound(names) for member in members}

	results = {}
	for member in members:
		values = found[member]
		missing = [name for name in names if not isinstance(values.get(name), str)]
		results[member] = TokenUnbound(missing) if missing else values
	return results


def _collect(template_ref: str, names: list[str], members: list[str], context: dict) -> dict | None:
	"""First value per member and token across the providers; None when any of them fails."""
	found = {member: {} for member in members}
	path = None
	try:
		paths = frappe.get_hooks(HOOK) or []
		for path in [paths] if isinstance(paths, str) else paths:
			answer = frappe.get_attr(path)(template_ref, list(names), list(members), dict(context))
			if not isinstance(answer, dict):
				_warn(path, "invalid result")
				return None
			for member in members:
				given = answer.get(member, {})
				if not isinstance(given, dict):
					_warn(path, "invalid result")
					return None
				for name in names:
					if name in given:
						found[member].setdefault(name, given[name])
	except Exception as error:  # noqa: BLE001 - fail closed; the message may hold a value
		_warn(path, type(error).__name__)
		return None
	return found


def _warn(path: str | None, what: str) -> None:
	try:
		frappe.logger("flow").warning(f"send token provider {path} blocked: {what}")
	except Exception:  # noqa: BLE001, S110 - logging must never turn a block into another error
		pass
