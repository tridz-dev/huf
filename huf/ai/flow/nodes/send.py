"""``send.message`` node: send one message to the person the run is about, always through the guard chain.

Config: ``gateway`` (Gateway name), ``recipient`` (a reference resolving to a phone number, or ``"$member"``:
the run's member, resolved by ``huf_send_recipient_providers`` at send time and again at delivery),
``template`` or ``text``
(exactly one), ``variables`` (token names, bound at send time by ``huf_send_token_providers``), ``category``
(``marketing`` | ``service``), optional ``header`` (media or location header) and ``language``.

Order (CONTRACTS.md section 7): bind tokens, then :func:`huf.ai.channels.outbound.guard.evaluate`, then the outbox.
No path reaches the outbox without an allowing guard result. Every decided outcome is recorded under the
step key (H-W2-13), so a re-delivered job or a re-run replays it instead of sending again (G2). Output ``status`` is one of:

- ``queued``: allowed and live; handed to the channel outbox (H-W2-15), which delivers, retries transient
  errors and binds the tokens again at delivery. The step never fails for a delivery error, so the engine
  never re-runs it;
- ``blocked`` with ``reason``: final (G2), the run goes on by its normal edge, nothing is retried;
- ``previewed``: the guard allowed it but the run is not live, so nothing was sent;
- ``deferred``: outside the send window; the run is parked (``park.defer_send``) and the whole chain runs
  again on wake.

Token values exist only in the dict the outbox hands to the transport at delivery: never in the output, context, trace or logs (G4).
A live guard pass with a cap commits the transaction, so the run context is persisted before it.
"""

from __future__ import annotations

import frappe

from huf.ai.channels.outbound import guard, guard_steps, recipient_binder, token_binder
from huf.ai.flow.nodes import split as split_node
from huf.ai.flow.runs import member as flow_member
from huf.ai.flow.runs import park
from huf.ai.flow.support import step_keys
from huf.ai.flow.testrun import gate as test_gate

CONFIG_KEYS = frozenset(
	{"gateway", "recipient", "template", "text", "variables", "category", "header", "language"}
)
CATEGORIES = ("marketing", "service")
#: Output statuses of a decided send: the engine never runs such a send again (G2).
FINAL_STATUSES = frozenset({"blocked", "queued", "sent", "previewed"})
WINDOW_DEFER_EXHAUSTED = "window_defer_exhausted"


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _done(node: dict, output: dict) -> dict:
	return {"status": "success", "output": output, "result": output, "next_node_id": node.get("next")}


def config_problem(config: dict) -> str | None:
	"""A readable reason the step cannot send with ``config``, or None. Preflight uses the same rules."""
	if "retry" in config:
		return "A send step cannot try again: a blocked send is final. Remove the retry setting."
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
	"""Whether this send really goes out: ``live_send AND NOT dry_run`` (G3, :func:`test_gate.is_live`)."""
	return test_gate.is_live(flow_run)


def exec_send_message(flow_run, node: dict, config: dict, settings: dict):
	from huf.ai.channels.outbound.outbox import RUN_CANCELLED
	from huf.ai.flow.engine import _context_of, _persist_context, _transition_run, run_cancelled

	problem = config_problem(config)
	if problem:
		return _failed(problem)
	gateway = config["gateway"]
	channel = channel_of(gateway)
	if not channel:
		return _failed("The channel (gateway) this step sends from was not found.")

	ctx = _context_of(flow_run, settings)
	key = step_keys.key_of(node)
	done = step_keys.replay(ctx.data, key)
	if done is not None:  # a re-delivered job: this step already completed, never send twice
		return done
	if config["category"] == "marketing" and split_node.is_holdout(ctx.data):  # decision 5: service still sends
		_leave_waiting(flow_run, node, _transition_run)
		return _final(flow_run, ctx, settings, node, key, {"status": "blocked", "reason": split_node.HOLDOUT_NO_CONTACT})
	member_ref = recipient_binder.is_member_ref(config["recipient"])
	recipient = None
	if not member_ref:
		raw = ctx.resolve(config["recipient"])
		recipient = guard_steps.normalise_recipient(raw) or (raw if isinstance(raw, str) else None)
	template = config.get("template") or None
	if template is not None:
		template = ctx.resolve(template)
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
		return _final(flow_run, ctx, settings, node, key, {"status": "blocked", "reason": reason})

	if member_ref:  # the number is resolved here and again at delivery, never stored (G4)
		try:
			raw = recipient_binder.resolve(gateway, member_key, refs)
		except recipient_binder.RecipientUnbound:
			return blocked(recipient_binder.RECIPIENT_UNBOUND)
		recipient = guard_steps.normalise_recipient(raw) or raw

	if token_names:  # values are bound again at delivery; here only "can every token be bound" (G4)
		if not member_key:
			return blocked(token_binder.TOKEN_UNBOUND)
		try:
			token_binder.bind(template or "", token_names, member_key, refs)
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
		"step_key": key,
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
		return _final(flow_run, ctx, settings, node, key, {"status": "previewed"})

	if not key:
		return _failed("This send step has no step key, so it cannot be queued safely.")
	if run_cancelled(flow_run.name, lock=True):  # cancelled (member removed) while this step ran
		return blocked(RUN_CANCELLED)
	refused = _enqueue(
		{
			**refs,
			"step_key": key,
			"member_key": member_key,
			"gateway": gateway,
			"channel": channel,
			"category": config["category"],
			"template": template,
			"language": config.get("language") or None,
			"recipient_ref": config["recipient"],
			"text_ref": config.get("text") or None,
			"token_names": token_names,
			"header": config.get("header"),
		}
	)
	if refused:
		return blocked(refused)
	return _final(flow_run, ctx, settings, node, key, {"status": "queued"})


def _leave_waiting(flow_run, node: dict, transition) -> None:
	"""After a deferred send was woken and is now decided: clear the park record, the member is active again."""
	waiting = park.is_reentry(flow_run, node)
	if not waiting or waiting.get("reason") != park.SEND_WINDOW_REASON:
		return
	transition(flow_run, {"waiting": None}, from_statuses=("Running",))
	if getattr(flow_run, "member_key", None):
		flow_member.set_status(flow_run.flow_id, flow_run.member_key, "Active")


def _body_params(token_names: list[str], values: dict, named: bool = False):
	"""A NAMED WhatsApp template takes a ``{token: value}`` map; any other a list in ``token_names`` order.

	``token_names`` is already in slot order (the compiler emits one name per slot), so the list is never
	re-sorted by name.
	"""
	if named:
		return {name: values[name] for name in token_names}
	return [values[name] for name in token_names]


def _final(flow_run, ctx, settings, node: dict, key: str, output: dict) -> dict:
	"""Record a decided send (blocked, previewed or queued) under its step key, so no re-run sends it (G2)."""
	from huf.ai.flow.engine import _persist_context

	result = _done(node, output)
	if key:
		step_keys.record(ctx.data, node.get("id") or "", key, result)
		ctx.dirty = True
		_persist_context(flow_run, ctx, settings)
	return result


def _enqueue(request: dict) -> str | None:
	"""Queue the allowed send on the outbox (H-W2-15). None when queued, else a reason code (a final block)."""
	from huf.ai.channels.outbound import outbox

	if request.get("channel") != "whatsapp":
		return "channel_unsupported"
	try:
		outbox.enqueue(request)
	except (outbox.LiteralRecipient, TypeError):  # a literal number, or a reference of an unsupported shape
		return "bad_recipient"
	return None
