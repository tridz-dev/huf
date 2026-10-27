"""Adaptive Card builders for Microsoft Teams (schema 1.5). Pure functions, no I/O.

Action buttons are ``Action.Execute`` with a verb and a ``data`` object that holds ONLY the opaque
Teams Action Session name: no user, role, price or credential data ever travels in a card. All text
is stripped of control characters, markdown-escaped and length bounded. Every builder returns a
card plus a plain-text fallback for the activity ``text``.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_URL = "http://adaptivecards.io/schemas/adaptive-card.json"
SCHEMA_VERSION = "1.5"
CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
MESSAGE_CONTENT_TYPE = "application/vnd.microsoft.activity.message"

VERB_APPROVE = "huf_approve"
VERB_REJECT = "huf_reject"
VERBS = (VERB_APPROVE, VERB_REJECT)

MAX_TITLE = 120
MAX_VALUE = 240
MAX_FACTS = 8
MAX_NOTICE = 400

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MD = re.compile(r"([\\`*_{}\[\]()#+!|<>~])")


def clean(value: Any, limit: int = MAX_VALUE) -> str:
	"""Control-char free, whitespace-collapsed, markdown-escaped, bounded text."""
	text = " ".join(_CTRL.sub("", str(value if value is not None else "")).split())
	return _MD.sub(r"\\\1", text[:limit])


def _plain(value: Any, limit: int) -> str:
	return " ".join(_CTRL.sub("", str(value if value is not None else "")).split())[:limit]


def _card(body: list, actions: list | None = None) -> dict:
	card: dict = {"type": "AdaptiveCard", "$schema": SCHEMA_URL, "version": SCHEMA_VERSION, "body": body}
	if actions:
		card["actions"] = actions
	card["msteams"] = {"width": "Full"}
	return card


def _title(text: str) -> dict:
	return {"type": "TextBlock", "text": clean(text, MAX_TITLE), "weight": "Bolder", "size": "Medium", "wrap": True}


def _facts(facts) -> list:
	rows = []
	for label, value in list(facts or [])[:MAX_FACTS]:
		if value is None or str(value) == "":
			continue
		rows.append({"title": clean(label, 40), "value": clean(value)})
	return [{"type": "FactSet", "facts": rows}] if rows else []


def _action(title: str, verb: str, session: str, style: str) -> dict:
	return {
		"type": "Action.Execute",
		"title": title,
		"verb": verb,
		"data": {"session": str(session)},
		"style": style,
	}


def approval_card(session_name: str, title: str, facts=None) -> tuple[dict, str]:
	"""Approve/Reject card. ``facts`` = [(label, value)] already limited to what the approver may see."""
	body = [_title(title)] + _facts(facts)
	actions = [
		_action("Approve", VERB_APPROVE, session_name, "positive"),
		_action("Reject", VERB_REJECT, session_name, "destructive"),
	]
	fallback = _plain(title, MAX_TITLE) + ". Open Huf to review and decide this approval."
	return _card(body, actions), fallback


def decided_card(verb_text: str, actor_name: str, when: str, title: str = "Approval") -> tuple[dict, str]:
	"""Terminal card with no actions: '<Approved|Rejected> by <name>'."""
	line = f"{_plain(verb_text, 20)} by {_plain(actor_name, 80)} at {_plain(when, 40)}"
	body = [_title(title), {"type": "TextBlock", "text": clean(line, MAX_NOTICE), "wrap": True}]
	return _card(body), line


def notice_card(text: str, title: str = "Huf") -> tuple[dict, str]:
	"""Notice or refusal card (no actions)."""
	body = [_title(title), {"type": "TextBlock", "text": clean(text, MAX_NOTICE), "wrap": True}]
	return _card(body), _plain(text, MAX_NOTICE)


def invoke_card_response(card: dict) -> dict:
	"""Body of the synchronous HTTP 200 answer to ``adaptiveCard/action`` (replaces the card)."""
	return {"statusCode": 200, "type": CARD_CONTENT_TYPE, "value": card}


def invoke_message_response(text: str) -> dict:
	"""Answer that shows a message to the clicker only and leaves the original card untouched."""
	return {"statusCode": 200, "type": MESSAGE_CONTENT_TYPE, "value": _plain(text, MAX_NOTICE)}


def activity_with_card(card: dict, fallback: str) -> dict:
	"""Message activity carrying the card; ``text`` is the plain fallback."""
	return {
		"type": "message",
		"text": _plain(fallback, 3000),
		"textFormat": "plain",
		"attachments": [{"contentType": CARD_CONTENT_TYPE, "content": card}],
	}
