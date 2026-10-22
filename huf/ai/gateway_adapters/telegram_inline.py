# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram inline mode: ``inline_query`` -> ``answerInlineQuery``; ``chosen_inline_result`` -> agent run.

Bot API shapes (https://core.telegram.org/bots/api): ``inline_query`` {id, from, query, offset, chat_type?};
``answerInlineQuery`` {inline_query_id, results (max 50), cache_time, is_personal, next_offset (max 64 bytes),
button: InlineQueryResultsButton {text, web_app | start_parameter}}; ``chosen_inline_result`` {result_id, from,
query, inline_message_id?}. ``savePreparedInlineMessage`` is Mini App only and out of scope.

Rules: only admitted senders get results (same policy as DMs, evaluated read-only: no pairing request is
created, no code is sent); unknown senders get ONE "Pair this bot" article plus a start_parameter button and no
data. Results come from deterministic resolvers only (no LLM inside the 10s inline window); resolvers run as
the gateway ``execution_user`` and never as Administrator. Respects ``Gateway.telegram_inline_enabled``.

Agent-powered default result: "Ask the assistant: <query>" is an article whose message is a "Thinking..."
placeholder. When the user picks it Telegram sends ``chosen_inline_result``; we enqueue a short-queue job that
runs the gateway default agent as the execution user and edits the placeholder with ``editMessageText``
(``inline_message_id``). Telegram only includes ``inline_message_id`` when the message carries an inline
keyboard, so the placeholder has a single inert "Working..." button, and the bot owner must enable inline
feedback (BotFather ``/setinlinefeedback``, set to 100%). Without feedback no chosen result arrives (or it has
no ``inline_message_id``): we degrade to doing nothing and log once per gateway.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Mapping

import frappe

MAX_RESULTS = 50
DEFAULT_CACHE_TIME = 30
MAX_QUERY_LEN = 256
MAX_NEXT_OFFSET_BYTES = 64
PAIR_START_PARAMETER = "pair"
ASK_PREFIX = "ask-"
WAIT_CALLBACK = "inl:wait"
PLACEHOLDER_TEXT = "Thinking..."
APOLOGY_TEXT = "Sorry, I couldn't answer that right now."
JOB = "huf.ai.gateway_adapters.telegram_inline.run_inline_job"
RATE_LIMIT = 6  # agent runs per sender per window
RATE_WINDOW = 60
MAX_ANSWER = 4096

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
	"""'Ask the assistant: <query>' article; picking it posts a placeholder the agent job later edits."""
	query = (query or "").strip()
	if not query:
		return []
	digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
	keyboard = {"inline_keyboard": [[{"text": "Working...", "callback_data": WAIT_CALLBACK}]]}
	return [
		_article(
			f"{ASK_PREFIX}{digest}",
			f"Ask the assistant: {query[:80]}",
			PLACEHOLDER_TEXT,
			description="Get an answer from the assistant",
			reply_markup=keyboard,
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
	if not inline_enabled(gateway):
		return _ack("inline mode disabled")
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


def inline_enabled(gateway) -> bool:
	return bool(getattr(gateway, "telegram_inline_enabled", 1))


def _cache_get(key: str):
	try:
		return frappe.cache().get_value(key)
	except Exception:
		return None


def _cache_put(key: str, value, ttl: int) -> None:
	try:
		frappe.cache().set_value(key, value, expires_in_sec=ttl)
	except Exception:
		pass


def rate_allow(gateway_name: str, sender_id: str) -> bool:
	"""Count one agent run for the sender; False once RATE_LIMIT runs happened inside the window."""
	key = f"huf:tginl:rl:{gateway_name}:{sender_id}"
	used = int(_cache_get(key) or 0)
	if used >= RATE_LIMIT:
		return False
	_cache_put(key, used + 1, RATE_WINDOW)
	return True


def _log_feedback_off_once(gateway_name: str) -> None:
	key = f"huf:tginl:nofb:{gateway_name}"
	if _cache_get(key):
		return
	_cache_put(key, 1, 86400)
	frappe.logger("huf").warning(
		f"Telegram gateway {gateway_name}: chosen_inline_result has no inline_message_id; enable inline "
		"feedback for the bot in BotFather (/setinlinefeedback, 100%) so the assistant can answer inline."
	)


def handle_chosen_inline_result(gateway, adapter, parsed, request) -> dict | None:
	chosen = _map(_map(parsed.raw).get("chosen_inline_result"))
	if not chosen:
		return None
	name = getattr(gateway, "name", "")
	sender_id = str(_map(chosen.get("from")).get("id") or "")
	result_id = str(chosen.get("result_id") or "")[:64]
	query = str(chosen.get("query") or "").strip()[:MAX_QUERY_LEN]
	# Log ids and lengths only, never the query text.
	frappe.logger("huf").info(
		f"Telegram gateway {name}: chosen_inline_result result_id={result_id} sender={sender_id} "
		f"query_len={len(query)}"
	)
	done = {"success": True, "handled": "chosen_inline_result"}
	if not inline_enabled(gateway) or not result_id.startswith(ASK_PREFIX) or not query:
		return done
	if not is_admitted(gateway, sender_id) or not execution_user(gateway):
		return done
	inline_message_id = str(chosen.get("inline_message_id") or "")
	if not inline_message_id:
		_log_feedback_off_once(name)
		return done
	from huf.ai.gateway_adapters import telegram_ingest as ing

	if not ing._first_delivery(name, f"inlinejob:{inline_message_id}"):
		return done
	if not rate_allow(name, sender_id):
		_edit(adapter, inline_message_id, "You are sending too many requests. Please try again in a minute.")
		return {**done, "note": "rate limited"}
	frappe.enqueue(
		JOB, queue="short", timeout=300, gateway_name=name, inline_message_id=inline_message_id,
		sender_id=sender_id, query=query,
	)
	return {**done, "note": "agent run queued"}


# -- job -------------------------------------------------------------------------------------------


def build_prompt(query: str) -> str:
	return (
		"[Telegram inline mode] The user asked from the inline box of any chat; your answer replaces a "
		"'Thinking...' message. Reply concisely in plain text or simple markdown (no buttons or media "
		f"blocks, under 3500 characters):\n\"\"\"\n{query}\n\"\"\""
	)


# seams (mocked in tests)
def _load_gateway(name: str):
	return frappe.get_doc("Gateway", name)


def _adapter(gateway):
	from huf.ai.gateway_webhook import get_gateway_adapter

	return get_gateway_adapter(gateway)


def _run_agent(gateway, sender_id: str, prompt: str, idem: str) -> dict:
	from huf.ai.agent_access import TRIGGER_GATEWAY, resolve_run_identity_and_authorize
	from huf.ai.agent_integration import run_agent_sync
	from huf.ai.gateway_service import _run_agent_serialised

	agent = gateway.default_agent
	identity = resolve_run_identity_and_authorize(
		frappe.get_doc("Agent", agent),
		TRIGGER_GATEWAY,
		{"execution_user": gateway.execution_user, "target_agent": agent},
	)
	if not identity.authorized:
		return {"success": False, "error": identity.reason}
	frappe.set_user(gateway.execution_user)
	ref = f"inline:{sender_id}"
	return _run_agent_serialised(
		run_agent_sync,
		lock_key=f"huf_gw_conv:{gateway.name}:{ref}",
		agent_name=agent,
		prompt=prompt,
		channel_id=f"gateway:{gateway.name}",
		external_id=ref,
		now=True,
		client_idempotency_key=idem,
	)


def clean_answer(result) -> str:
	"""Visible answer text: button/media fences stripped, capped; '' when the run produced nothing."""
	if not isinstance(result, Mapping) or result.get("success") is False:
		return ""
	text = str(result.get("response") or "").strip()
	if not text:
		return ""
	from huf.ai.gateway_adapters import telegram_buttons, telegram_media_reply

	for rx in (telegram_buttons._FENCE_RE, telegram_media_reply._FENCE_RE):
		text = rx.sub("", text)
	return re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_ANSWER * 2]


def _edit(adapter, inline_message_id: str, markdown: str) -> bool:
	"""editMessageText on the inline message: HTML first, plain-text fallback, 4096 cap."""
	from huf.ai.gateway_adapters import telegram_format as fmt
	from huf.ai.gateway_adapters.telegram_client import TelegramApiError

	parts = fmt.render_parts(markdown, fmt.MODE_HTML, MAX_ANSWER)
	part = parts[0] if parts else fmt.RenderedPart(markdown[:MAX_ANSWER], "", markdown[:MAX_ANSWER])
	base = {"inline_message_id": inline_message_id, "link_preview_options": {"is_disabled": True}}
	attempts = [{"text": part.text, "parse_mode": part.parse_mode}] if part.parse_mode else []
	attempts.append({"text": part.plain[:MAX_ANSWER]})
	for extra in attempts:
		try:
			adapter.client.call("editMessageText", {**base, **extra})
			return True
		except TelegramApiError as exc:
			if exc.message_not_modified:
				return True
			if not exc.parse_error:
				break
		except Exception:
			break
	return False


def run_inline_job(gateway_name: str, inline_message_id: str, sender_id: str, query: str) -> dict:
	"""Background job: run the default agent as the execution user, then edit the placeholder."""
	log = frappe.logger("huf")
	gateway = _load_gateway(gateway_name)
	adapter = _adapter(gateway)
	if not inline_enabled(gateway) or not execution_user(gateway) or not is_admitted(gateway, sender_id):
		return {"result": "skipped", "reason": "not_allowed"}
	text = ""
	try:
		text = clean_answer(_run_agent(gateway, sender_id, build_prompt(query), f"tginl:{inline_message_id}"))
	except Exception as exc:
		log.warning(f"Telegram inline {gateway_name}: agent run failed ({type(exc).__name__})")
	if not text:
		_edit(adapter, inline_message_id, APOLOGY_TEXT)
		return {"result": "failed"}
	return {"result": "answered" if _edit(adapter, inline_message_id, text) else "edit_failed"}


def dispatch(gateway, adapter, parsed, request) -> dict | None:
	"""Entry for the ``unsupported`` kind (parse_update has no inline branch); None for other updates."""
	raw = _map(parsed.raw)
	if "inline_query" in raw:
		return handle_inline_query(gateway, adapter, parsed, request)
	if "chosen_inline_result" in raw:
		return handle_chosen_inline_result(gateway, adapter, parsed, request)
	return None
