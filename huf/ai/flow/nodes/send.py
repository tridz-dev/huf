"""``send.message`` node: send one message to the person the run is about, always through the guard chain.

Config: ``gateway`` (Gateway name), ``recipient`` (value or reference, a phone number), ``template`` or ``text``
(exactly one), ``variables`` (token names, bound at send time by ``huf_send_token_providers``), ``category``
(``marketing`` | ``service``), optional ``header`` (media or location header) and ``language``.

Order (CONTRACTS.md section 7): bind tokens, then :func:`huf.ai.channels.guard.evaluate`, then the transport.
No path reaches the transport without an allowing guard result. Output ``status`` is one of:

- ``sent``: the transport accepted it;
- ``blocked`` with ``reason``: final (G2), the run goes on by its normal edge, nothing is retried;
- ``previewed``: the guard allowed it but the run is not live, so nothing was sent;
- ``deferred``: outside the send window; the run is parked (``park.defer_send``) and the whole chain runs
  again on wake.

Token values exist only in the dict handed to the transport: never in the output, context, trace or logs (G4).
A live guard pass with a cap commits the transaction, so the run context is persisted before it.
"""

from __future__ import annotations

import frappe

from huf.ai.channels import guard, guard_steps, token_binder
from huf.ai.flow.runs import member as flow_member
from huf.ai.flow.runs import park
from huf.ai.flow.testrun import gate as test_gate

CONFIG_KEYS = frozenset(
	{"gateway", "recipient", "template", "text", "variables", "category", "header", "language"}
)
CATEGORIES = ("marketing", "service")
WINDOW_DEFER_EXHAUSTED = "window_defer_exhausted"


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _done(node: dict, output: dict) -> dict:
	return {"status": "success", "output": output, "result": output, "next_node_id": node.get("next")}


def config_problem(config: dict) -> str | None:
	"""A readable reason the step cannot send with ``config``, or None. Preflight uses the same rules."""
	if set(config) - CONFIG_KEYS:
		return "This send step has settings it does not use. Remove them and save again."
	if not isinstance(config.get("gateway"), str) or not config["gateway"].strip():
		return "Choose the channel (gateway) this step sends from."
	if config.get("recipient") in (None, ""):
		return "Choose who this step sends to."
	if config.get("category") not in CATEGORIES:
		return "Choose whether this is a marketing or a service message."
	has_template, has_text = bool(config.get("template")), bool(config.get("text"))
	if has_template == has_text:
		return "Choose a template or write a text, not both."
	variables = config.get("variables")
	if variables is not None and not (
		isinstance(variables, list) and all(isinstance(v, str) and v for v in variables)
	):
		return "Variables must be a list of token names."
	return None


def channel_of(gateway: str) -> str:
	"""Lowercase provider of the Gateway (``whatsapp``), or "" when it does not exist."""
	return (frappe.db.get_value("Gateway", gateway, "provider") or "").strip().lower()


def is_live(flow_run) -> bool:
	"""Whether this send really goes out. H-W2-05 replaces this with ``live_send AND NOT dry_run``."""
	return not test_gate.is_test_run(flow_run)


def exec_send_message(flow_run, node: dict, config: dict, settings: dict):
	from huf.ai.flow.engine import _context_of, _persist_context, _transition_run

	problem = config_problem(config)
	if problem:
		return _failed(problem)
	gateway = config["gateway"]
	channel = channel_of(gateway)
	if not channel:
		return _failed("The channel (gateway) this step sends from was not found.")

	ctx = _context_of(flow_run, settings)
	raw = ctx.resolve(config["recipient"])
	recipient = guard_steps.normalise_recipient(raw) or (raw if isinstance(raw, str) else None)
	template = config.get("template") or None
	if template is not None:
		template = ctx.resolve(template)
	text = ctx.resolve(config["text"]) if config.get("text") else None
	token_names = list(config.get("variables") or [])
	member_key = getattr(flow_run, "member_key", None)
	node_id = node.get("id") or ""
	refs = {
		"flow_id": getattr(flow_run, "flow_id", None),
		"flow_version": str(getattr(flow_run, "flow_version", "") or ""),
		"run_id": flow_run.name,
		"node_id": node_id,
	}

	def blocked(reason: str) -> dict:
		_leave_waiting(flow_run, node, _transition_run)
		return _done(node, {"status": "blocked", "reason": reason})

	values: dict = {}
	if token_names:
		if not member_key:
			return blocked(token_binder.TOKEN_UNBOUND)
		try:
			values = token_binder.bind(template or "", token_names, member_key, refs)
		except token_binder.TokenUnbound:
			return blocked(token_binder.TOKEN_UNBOUND)

	live = is_live(flow_run)
	request = {
		"member_key": member_key,
		"gateway": gateway,
		"channel": channel,
		"category": config["category"],
		"recipient": recipient,
		"template": template,
		"token_names": token_names,
		**refs,
		"step_key": "",
		"live": live,
	}
	_persist_context(flow_run, ctx, settings)  # a live guard pass with a cap commits
	result = guard.evaluate(request, header=config.get("header"))
	if result.defer_until is not None:
		parked = park.defer_send(flow_run, node, result.defer_until, member_key)
		if parked is None:
			return blocked(WINDOW_DEFER_EXHAUSTED)
		if member_key:
			flow_member.set_status(flow_run.flow_id, member_key, "Waiting", node_id)
		return parked
	if not result.allowed:
		return blocked(result.reason or "unknown")
	_leave_waiting(flow_run, node, _transition_run)
	if not live:
		return _done(node, {"status": "previewed"})

	refused = _transport(gateway, channel, recipient, template, text, token_names, values, config, refs)
	if refused:
		return _failed(refused)
	return _done(node, {"status": "sent"})


def _leave_waiting(flow_run, node: dict, transition) -> None:
	"""After a deferred send was woken and is now decided: clear the park record, the member is active again."""
	waiting = park.is_reentry(flow_run, node)
	if not waiting or waiting.get("reason") != park.SEND_WINDOW_REASON:
		return
	transition(flow_run, {"waiting": None}, from_statuses=("Running",))
	if getattr(flow_run, "member_key", None):
		flow_member.set_status(flow_run.flow_id, flow_run.member_key, "Active")


def _body_params(token_names: list[str], values: dict):
	"""Positional templates (``1``, ``2``...) take a list in order; named ones a map."""
	if all(name.isdigit() for name in token_names):
		return [values[name] for name in sorted(token_names, key=int)]
	return {name: values[name] for name in token_names}


def _transport(gateway, channel, recipient, template, text, token_names, values, config, refs) -> str | None:
	"""Hand the send to the channel. None when accepted, else a readable reason (no values in it)."""
	if channel != "whatsapp":
		return f"Sending from a {channel} channel is not supported by this step yet."
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.whatsapp import management

	refused = management._send_authority(gateway)  # write authority of the run user on the gateway
	if refused:
		return "This run's user may not send from this channel."
	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account")
	phone = bridge.normalize_phone(recipient)
	if template:
		answer = bridge.send_template(
			account,
			phone,
			template,
			_body_params(token_names, values) if token_names else [],
			[config["header"]] if config.get("header") else [],
			language_code=config.get("language") or None,
			gateway_name=gateway,
			run_id=refs["run_id"],
			force_graph=True,
			redact_params=True,
		)
	else:
		answer = bridge.send_text(account, phone, str(text), gateway_name=gateway)
	if isinstance(answer, dict) and answer.get("success") is False:
		return "The channel did not accept the message."
	return None
