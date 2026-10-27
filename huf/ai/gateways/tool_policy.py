"""Generic confirm-before-write gate and per-gateway tool policy (WP A8).

Called from the tool wrapper in ``huf.ai.sdk_tools`` before a tool runs. Everything here is a
no-op for runs that did not originate from a gateway, so non-gateway behaviour is unchanged.

Three independent checks, applied in order for a gateway-originated run:

1. Tool policy (optional ``Gateway Tool Policy`` records). A channel-scoped policy overrides the
   gateway-wide one for that conversation. Allow list: only the listed tools run. Deny list:
   the listed tools are refused. No policy means no restriction.
2. Exfiltration guard. Once a Slack READ tool has run in this agent run, the Slack SEND tools
   are refused when they target a different channel than the one the run came from, unless an
   applicable policy sets ``allow_cross_channel_send``. The flag is tracked per agent run in
   the cache (it is cheap, per-run state; fail-closed when the origin channel is unknown).
3. Confirmation. A tool flagged ``requires_confirmation`` is never executed by the gate. The
   call is handed to a registered confirmer (``set_confirmer``); with no confirmer registered
   the call is refused (fail closed). The existing Agent Execution Approval is execution-kind
   specific and cannot park an arbitrary tool call, so no backend is wired here yet.
"""

from __future__ import annotations

import json
import re

import frappe

POLICY_DOCTYPE = "Gateway Tool Policy"
ALLOW = "Allow list"
DENY = "Deny list"

SLACK_READ_TOOLS = frozenset({"slack_get_channel_history", "slack_search_messages"})
SLACK_SEND_TOOLS = frozenset({"slack_send_message", "slack_send_thread_reply"})

_CTX_PREFIX = "huf_a8_ctx:"
_READ_PREFIX = "huf_a8_slack_read:"
_TTL = 6 * 3600

_CONFIRMER = None


def set_confirmer(fn) -> None:
	"""Register ``fn(context, tool_name, args) -> dict | None``.

	A returned dict is handed to the model as the tool result (the call is NOT executed by the
	gate); ``None`` means the confirmer could not take the request and the call is refused."""
	global _CONFIRMER
	_CONFIRMER = fn


def _cache():
	cache = frappe.cache
	return cache() if callable(cache) and not hasattr(cache, "get_value") else cache


def _name_variants(name: str) -> set[str]:
	name = str(name or "").strip()
	return {name, re.sub(r"[^a-zA-Z0-9_-]", "_", name)} - {""}


def parse_tools(text) -> set[str]:
	if isinstance(text, (list, tuple, set)):
		items = [str(t) for t in text]
	else:
		items = re.split(r"[\n,]", str(text or ""))
	return {t.strip() for t in items if t and t.strip()}


def _get(obj, key, default=None):
	if isinstance(obj, dict):
		return obj.get(key, default)
	return getattr(obj, key, default)


# ------------------------------------------------------------------ run context
def resolve_gateway_context(agent_run_id) -> dict | None:
	"""Map an agent run to its originating Gateway Event: ``{gateway, channel, event}`` or None.

	Gateway runs carry ``idempotency_key == "gw:<Gateway Event name>"``; Gateway Event.agent_run
	is only filled after the run, so it cannot be used while tools execute."""
	if not agent_run_id:
		return None
	key = f"{_CTX_PREFIX}{agent_run_id}"
	cache = _cache()
	cached = cache.get_value(key)
	if cached is not None and cached != "":
		return None if cached == "-" else (json.loads(cached) if isinstance(cached, (str, bytes)) else cached)
	ctx = None
	idem = frappe.db.get_value("Agent Run", agent_run_id, "idempotency_key")
	if isinstance(idem, str) and idem.startswith("gw:"):
		row = frappe.db.get_value(
			"Gateway Event", idem[3:], ["name", "gateway", "conversation_id"], as_dict=True
		)
		if row:
			ctx = {"gateway": _get(row, "gateway"), "channel": _get(row, "conversation_id"), "event": _get(row, "name")}
	cache.set_value(key, json.dumps(ctx) if ctx else "-", expires_in_sec=_TTL)
	return ctx


# ------------------------------------------------------------------ policy
def get_policy(gateway, channel=None) -> dict | None:
	"""Applicable policy: channel-scoped if one exists for ``channel``, else gateway-wide, else None."""
	gateway = getattr(gateway, "name", gateway)
	rows = frappe.get_all(
		POLICY_DOCTYPE,
		filters={"gateway": gateway},
		fields=["scope", "mode", "tools", "allow_cross_channel_send"],
	) or []
	chosen = None
	for row in rows:
		scope = (_get(row, "scope") or "").strip()
		if scope and channel and scope == str(channel):
			chosen = row
			break
		if not scope and chosen is None:
			chosen = row
	if chosen is None:
		return None
	return {
		"mode": _get(chosen, "mode") or ALLOW,
		"tools": parse_tools(_get(chosen, "tools")),
		"allow_cross_channel_send": bool(_get(chosen, "allow_cross_channel_send")),
	}


def get_allowed_tools(gateway, event=None):
	"""Explicit allow-list for this gateway/event, or None when no allow-list restricts tools
	(no policy, or a deny-list policy: use :func:`is_tool_allowed` for the full answer)."""
	policy = get_policy(gateway, _get(event, "conversation_id") if event is not None else None)
	if policy and policy["mode"] == ALLOW:
		return set(policy["tools"])
	return None


def is_tool_allowed(gateway, event, tool_name) -> bool:
	policy = get_policy(gateway, _get(event, "conversation_id") if event is not None else None)
	if not policy:
		return True
	listed_names = set().union(*(_name_variants(t) for t in policy["tools"])) if policy["tools"] else set()
	listed = bool(_name_variants(tool_name) & listed_names)
	return listed if policy["mode"] == ALLOW else not listed


# ------------------------------------------------------------------ gate
def _denied(message: str, **extra) -> str:
	return json.dumps({"error": message, "denied": True, **extra})


def _channel_arg(args: dict) -> str:
	return str((args or {}).get("channel") or "").strip()


def check_tool_call(tool_name, args, agent_run_id, requires_confirmation=False) -> str | None:
	"""Return a JSON tool result string if the call must NOT run, else None (proceed)."""
	try:
		ctx = resolve_gateway_context(agent_run_id)
	except Exception:
		# Cannot identify the run: treat as a non-gateway run (behaviour unchanged).
		return None
	if not ctx:
		return None
	try:
		gateway, channel = ctx["gateway"], ctx.get("channel")
		event = {"conversation_id": channel}
		if not is_tool_allowed(gateway, event, tool_name):
			return _denied(f"Tool '{tool_name}' is not allowed by this gateway's tool policy.")
		names = _name_variants(tool_name)
		if names & SLACK_SEND_TOOLS and _cache().get_value(f"{_READ_PREFIX}{agent_run_id}"):
			target = _channel_arg(args)
			if not target or target != str(channel or ""):
				policy = get_policy(gateway, channel)
				if not (policy and policy["allow_cross_channel_send"]):
					return _denied(
						"Sending to a different Slack channel after reading Slack messages in the "
						"same run is not allowed.",
						reason="exfiltration_guard",
					)
		if requires_confirmation:
			if _CONFIRMER is not None:
				out = _CONFIRMER(ctx, tool_name, dict(args or {}))
				if out is not None:
					return json.dumps(out, default=str)
			return _denied(
				f"Tool '{tool_name}' requires confirmation, which is not available for this "
				"gateway yet. It was not executed.",
				requires_confirmation=True,
			)
	except Exception:
		# Gateway run, but the gate itself failed: fail closed.
		return _denied("Tool call blocked: the gateway tool policy could not be evaluated.")
	return None


def note_tool_executed(tool_name, agent_run_id) -> None:
	"""Record that a Slack read tool ran in this run (arms the exfiltration guard)."""
	if not agent_run_id or not (_name_variants(tool_name) & SLACK_READ_TOOLS):
		return
	try:
		if resolve_gateway_context(agent_run_id):
			_cache().set_value(f"{_READ_PREFIX}{agent_run_id}", 1, expires_in_sec=_TTL)
	except Exception:
		pass
