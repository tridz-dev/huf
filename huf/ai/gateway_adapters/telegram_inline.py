# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram inline mode: ``inline_query`` -> ``answerInlineQuery`` and ``chosen_inline_result`` (record only).

Bot API shapes (https://core.telegram.org/bots/api): ``inline_query`` {id, from, query, offset, chat_type?};
``answerInlineQuery`` {inline_query_id, results (max 50), cache_time, is_personal, next_offset (max 64 bytes),
button: InlineQueryResultsButton {text, web_app | start_parameter}}; ``chosen_inline_result`` {result_id, from,
query, inline_message_id?}. ``savePreparedInlineMessage`` is Mini App only and out of scope.

Rules: only admitted senders get results (same policy as DMs, evaluated read-only: no pairing request is
created, no code is sent); unknown senders get ONE "Pair this bot" article plus a start_parameter button and no
data. Results come from deterministic resolvers only (no LLM inside the 10s inline window); resolvers run as
the gateway ``execution_user`` and never as Administrator. The default result posts the question as plain
text; a Run action is not wired (inline-sent messages carry no chat id for callback verification).
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

import frappe

MAX_RESULTS = 50
DEFAULT_CACHE_TIME = 30
MAX_QUERY_LEN = 256
MAX_NEXT_OFFSET_BYTES = 64
PAIR_START_PARAMETER = "pair"
RUN_CALLBACK_PREFIX = "inl:run"

_RESOLVERS: dict[str, Callable[[str, dict], list[dict]]] = {}


def register_resolver(name: str, fn: Callable[[str, dict], list[dict]]) -> None:
	"""Register ``fn(query, user_ctx) -> list[InlineQueryResult dict]``. Same name replaces."""
	_RESOLVERS[name] = fn


def unregister_resolver(name: str) -> None:
	_RESOLVERS.pop(name, None)


def resolver_names() -> list[str]:
	return list(_RESOLVERS)


def _article(result_id: str, title: str, text: str, description: str = "", reply_markup=None) -> dict:
	out: dict[str, Any] = {
		"type": "article",
		"id": result_id,
		"title": title[:256],
		"input_message_content": {"message_text": text[:4096]},
	}
	if description:
		out["description"] = description[:256]
	if reply_markup:
		out["reply_markup"] = reply_markup
	return out


def default_resolver(query: str, user_ctx: dict) -> list[dict]:
	"""'Ask the assistant: <query>' article that posts the question as text (no button: inline-sent messages
	carry no chat id, so a signed callback could not be verified; add a Run action when that path exists)."""
	query = (query or "").strip()
	if not query:
		return []
	digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
	return [
		_article(
			f"ask-{digest}",
			f"Ask the assistant: {query[:80]}",
			f"Ask the assistant: {query[:500]}",
			description="Send this question as a message",
		)
	]


register_resolver("default", default_resolver)


# -- parsing ---------------------------------------------------------------------------------


def _map(value) -> Mapping[str, Any]:
	return value if isinstance(value, Mapping) else {}


def parse_inline_query(raw: Mapping[str, Any]) -> dict | None:
	iq = _map(raw.get("inline_query"))
	if not iq or not iq.get("id"):
		return None
	sender = _map(iq.get("from"))
	return {
		"id": str(iq["id"]),
		"sender_id": str(sender.get("id") or ""),
		"display_name": " ".join(
			p for p in (sender.get("first_name"), sender.get("last_name")) if p
		) or str(sender.get("username") or ""),
		"is_bot": bool(sender.get("is_bot")),
		"query": str(iq.get("query") or "")[:MAX_QUERY_LEN],
		"offset": str(iq.get("offset") or ""),
		"chat_type": str(iq.get("chat_type") or ""),
	}


def parse_offset(offset: str) -> int:
	try:
		return max(0, int(offset or 0))
	except (TypeError, ValueError):
		return 0


# -- admission (read-only) -------------------------------------------------------------------


def is_admitted(gateway, sender_id: str) -> bool:
	"""DM admission without side effects: no pairing request, no code reply."""
	from huf.ai import gateway_service as svc

	if not sender_id or svc._sender_negative_state(gateway, sender_id):
		return False
	policy = gateway.direct_policy or "Allow list"
	if policy == "Open":
		return True
	if policy in ("Pairing", "Allow list"):
		return bool(svc._has_access_entry(gateway, "Sender", sender_id))
	return False


def execution_user(gateway) -> str | None:
	user = (gateway.get("execution_user") if hasattr(gateway, "get") else None) or getattr(
		gateway, "execution_user", None
	)
	if not user or user in ("Administrator", "Guest"):
		return None
	return str(user)


# -- results ---------------------------------------------------------------------------------


def collect_results(query: str, user_ctx: dict) -> list[dict]:
	"""Run resolvers as the execution user. A failing resolver is skipped; ids are de-duplicated."""
	user = user_ctx.get("user")
	if not user:
		return []
	try:
		previous = frappe.session.user
	except Exception:
		previous = None
	results: list[dict] = []
	seen: set[str] = set()
	try:
		frappe.set_user(user)
		for name, fn in list(_RESOLVERS.items()):
			try:
				items = fn(query, dict(user_ctx)) or []
			except Exception as exc:
				frappe.logger("huf").warning(f"Telegram inline resolver {name} failed: {type(exc).__name__}")
				continue
			for item in items:
				rid = str(_map(item).get("id") or "")
				if not rid or len(rid) > 64 or rid in seen or not _map(item).get("type"):
					continue
				seen.add(rid)
				results.append(dict(item))
	finally:
		if previous:
			frappe.set_user(previous)
	return results


def build_answer(inline_query_id: str, results: list[dict], offset: int = 0, page_size: int = MAX_RESULTS,
	cache_time: int = DEFAULT_CACHE_TIME) -> dict:
	page_size = max(1, min(int(page_size), MAX_RESULTS))
	page = results[offset : offset + page_size]
	payload: dict[str, Any] = {
		"inline_query_id": inline_query_id,
		"results": page,
		"cache_time": cache_time,
		"is_personal": True,
	}
	if offset + page_size < len(results):
		nxt = str(offset + page_size)
		if len(nxt.encode("utf-8")) <= MAX_NEXT_OFFSET_BYTES:
			payload["next_offset"] = nxt
	return payload


def build_pair_answer(inline_query_id: str) -> dict:
	"""Single 'Pair this bot' result; no data. cache_time 0 so pairing takes effect immediately."""
	return {
		"inline_query_id": inline_query_id,
		"results": [
			_article("pair", "Pair this bot", "Open a chat with this bot to pair your account.",
				description="You are not paired yet")
		],
		"cache_time": 0,
		"is_personal": True,
		"button": {"text": "Pair this bot", "start_parameter": PAIR_START_PARAMETER},
	}


# -- handlers --------------------------------------------------------------------------------


def _ack(note: str) -> dict:
	return {"success": True, "ignored": "inline_query", "note": note}


def handle_inline_query(gateway, adapter, parsed, request) -> dict | None:
	q = parse_inline_query(parsed.raw)
	if q is None:
		return None
	if q["is_bot"]:
		return _ack("bot sender ignored")
	admitted = is_admitted(gateway, q["sender_id"])
	user = execution_user(gateway) if admitted else None
	if not admitted:
		payload = build_pair_answer(q["id"])
	elif not user:
		payload = build_answer(q["id"], [])
	else:
		ctx = {"user": user, "sender_id": q["sender_id"], "chat_type": q["chat_type"], "gateway": gateway.name}
		payload = build_answer(q["id"], collect_results(q["query"], ctx), parse_offset(q["offset"]))
	try:
		adapter.client.call("answerInlineQuery", payload)
	except Exception as exc:
		from huf.ai.gateway_service import _redact_error_text

		frappe.logger("huf").warning(f"Telegram inline answer failed: {_redact_error_text(str(exc))}")
		return _ack("answer failed")
	return {"success": True, "handled": "inline_query", "results": len(payload["results"])}


def handle_chosen_inline_result(gateway, adapter, parsed, request) -> dict | None:
	chosen = _map(_map(parsed.raw).get("chosen_inline_result"))
	if not chosen:
		return None
	sender = _map(chosen.get("from"))
	# Record only: ids and lengths, never the query text; no agent run.
	frappe.logger("huf").info(
		f"Telegram gateway {getattr(gateway, 'name', '')}: chosen_inline_result result_id="
		f"{str(chosen.get('result_id') or '')[:64]} sender={sender.get('id')} "
		f"query_len={len(str(chosen.get('query') or ''))}"
	)
	return {"success": True, "handled": "chosen_inline_result"}


def dispatch(gateway, adapter, parsed, request) -> dict | None:
	"""Entry for the ``unsupported`` kind (parse_update has no inline branch); None for other updates."""
	raw = _map(parsed.raw)
	if "inline_query" in raw:
		return handle_inline_query(gateway, adapter, parsed, request)
	if "chosen_inline_result" in raw:
		return handle_chosen_inline_result(gateway, adapter, parsed, request)
	return None
