"""Slack Block Kit builders.

Every high-level builder returns ``Rendered(blocks, fallback)``: the blocks to send plus a
plain-text ``fallback`` for the message ``text`` (notifications, screen readers, clients
that cannot render blocks). Buttons carry ONLY a Gateway Action Session name (plus an
optional short choice label in ``action_id``); business data stays server-side.
"""

from __future__ import annotations

import re
from typing import NamedTuple

SECTION_TEXT_LIMIT = 3000
BUTTON_TEXT_LIMIT = 75
_CHOICE_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_STYLES = (None, "primary", "danger")


class Rendered(NamedTuple):
	blocks: list
	fallback: str


def escape_mrkdwn(text) -> str:
	"""Escape the three characters Slack treats as control characters in mrkdwn."""
	return str(text if text is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _clip(text: str, limit: int) -> str:
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _plain(text) -> str:
	return escape_mrkdwn(text).replace("*", "").replace("_", "").replace("`", "").replace("~", "")


def section_block(text: str, *, escape: bool = True) -> dict:
	body = escape_mrkdwn(text) if escape else str(text)
	return {"type": "section", "text": {"type": "mrkdwn", "text": _clip(body, SECTION_TEXT_LIMIT)}}


def section_text(text: str, *, escape: bool = True) -> Rendered:
	block = section_block(text, escape=escape)
	return Rendered([block], block["text"]["text"])


def action_id_for(session_name: str, choice: str | None = None) -> str:
	return f"{session_name}.{choice}" if choice else str(session_name)


def parse_action_id(action_id: str) -> tuple[str, str | None]:
	"""Inverse of ``action_id_for``: (session_name, choice or None)."""
	name, sep, choice = str(action_id or "").rpartition(".")
	return (name, choice) if sep and name else (str(action_id or ""), None)


def confirm_dialog(title: str, text: str, confirm: str = "Yes", deny: str = "Cancel") -> dict:
	return {
		"title": {"type": "plain_text", "text": _clip(str(title), 100)},
		"text": {"type": "mrkdwn", "text": _clip(escape_mrkdwn(text), 300)},
		"confirm": {"type": "plain_text", "text": _clip(str(confirm), 30)},
		"deny": {"type": "plain_text", "text": _clip(str(deny), 30)},
	}


def button(text: str, session_name: str, *, choice: str | None = None, style: str | None = None,
	confirm: dict | None = None) -> dict:
	if not session_name:
		raise ValueError("button needs an action session name")
	if style not in _STYLES:
		raise ValueError("style must be primary or danger")
	if choice is not None and not _CHOICE_RE.match(choice):
		raise ValueError("choice must be 1-32 chars of a-z, 0-9, _")
	element = {
		"type": "button",
		"text": {"type": "plain_text", "text": _clip(str(text), BUTTON_TEXT_LIMIT)},
		"action_id": action_id_for(session_name, choice),
		"value": str(session_name),
	}
	if style:
		element["style"] = style
	if confirm:
		element["confirm"] = confirm
	return element


def actions_block(*elements: dict, block_id: str | None = None) -> dict:
	if not elements or len(elements) > 25:
		raise ValueError("an actions block needs 1-25 elements")
	block = {"type": "actions", "elements": list(elements)}
	if block_id:
		block["block_id"] = block_id
	return block


def buttons(*elements: dict) -> Rendered:
	labels = " / ".join(e["text"]["text"] for e in elements)
	return Rendered([actions_block(*elements)], labels)


def approval_card(title: str, details: str, session_name: str, *, approve_label: str = "Approve",
	reject_label: str = "Reject", confirm_approve: dict | None = None) -> Rendered:
	"""Title + details + Approve/Reject buttons sharing ONE session (first click wins)."""
	head = f"*{escape_mrkdwn(title)}*\n{escape_mrkdwn(details)}" if details else f"*{escape_mrkdwn(title)}*"
	blocks = [
		section_block(head, escape=False),
		actions_block(
			button(approve_label, session_name, choice="approve", style="primary", confirm=confirm_approve),
			button(reject_label, session_name, choice="reject", style="danger"),
		),
	]
	fallback = f"{_plain(title)}: {_plain(details)}".strip(": ") + f" ({approve_label} or {reject_label} in Slack)"
	return Rendered(blocks, fallback)


def status_line(text: str, *, icon: str | None = None) -> Rendered:
	"""Final one-line status that replaces buttons after a decision."""
	prefix = f"{icon} " if icon else ""
	body = f"{prefix}{escape_mrkdwn(text)}"
	return Rendered([{"type": "context", "elements": [{"type": "mrkdwn", "text": _clip(body, 3000)}]}],
		f"{prefix}{_plain(text)}")
