"""The believable output of a step a test run skipped: a sentence and a sample result.

``{"simulated": true, "summary": "Would send email to ada@example.com", ...sample fields}``

Pure functions (no database), so the wording is unit tested on its own. The sample fields have the same
names the real tool returns, so later steps that read them keep working in a test run.
"""

from __future__ import annotations

from typing import Any

from huf.ai.flow.support.humanize import format_scalar, label_for
from huf.ai.flow.testrun.effects import CHANGES, SENDS

SAMPLE_ID = "sample-0001"
SAMPLE_TS = "1700000000.000100"
NOTE = "Skipped in a test run: nothing was sent or changed."
_MAX_TARGET = 60


def _first(args: dict, *keys: str) -> str:
	for key in keys:
		value = args.get(key)
		text = format_scalar(value) if value not in (None, "") else None
		if text:
			return text if len(text) <= _MAX_TARGET else text[: _MAX_TARGET - 1].rstrip() + "…"
	return ""


def _to(prefix: str, target: str, fallback: str) -> str:
	return f"{prefix} {target}" if target else fallback


def _summary_and_sample(tool_id: str, effect: str, args: dict) -> tuple[str, dict]:
	"""(``Would ...`` sentence, sample result fields) for one skipped call."""
	if tool_id == "gmail_send_email":
		return (
			_to("Would send email to", _first(args, "to"), "Would send email"),
			{"id": SAMPLE_ID, "threadId": SAMPLE_ID, "labelIds": ["SENT"]},
		)
	if tool_id in ("slack_send_message", "slack_send_thread_reply"):
		where = _first(args, "channel")
		return _to("Would post a Slack message in", where, "Would post a Slack message"), {"ok": True, "ts": SAMPLE_TS, "channel": where or "C000SAMPLE"}
	if tool_id == "discord_send_message":
		return _to("Would post a Discord message in", _first(args, "channel_id", "channel"), "Would post a Discord message"), {"id": SAMPLE_ID}
	if tool_id in ("google_chat_send_message", "google_chat_send_card"):
		return _to("Would post a Google Chat message in", _first(args, "space", "space_name"), "Would post a Google Chat message"), {"name": SAMPLE_ID}
	if tool_id in ("whatsapp", "telegram", "messenger", "gateway_send", "gateway_reply"):
		kind = {"whatsapp": "WhatsApp", "telegram": "Telegram", "messenger": "Messenger"}.get(tool_id, "chat")
		return _to(f"Would send a {kind} message to", _first(args, "to", "recipient", "chat_id", "phone", "contact"), f"Would send a {kind} message"), {"sent": True, "message_id": SAMPLE_ID}
	if tool_id == "http_request":
		method = (_first(args, "method") or "POST").upper()
		url = _first(args, "url")
		return (
			f"Would send a {method} request to {url}" if url else f"Would send a {method} request",
			{"success": True, "status_code": 200, "headers": {}, "body": {}},
		)
	if tool_id == "gsheets_update":
		return _to("Would update the sheet range", _first(args, "range"), "Would update a Google Sheet"), {"updatedCells": 1}
	if tool_id == "gsheets_create":
		return _to("Would create a Google Sheet called", _first(args, "title"), "Would create a Google Sheet"), {"spreadsheetId": SAMPLE_ID}
	if tool_id == "gmail_create_draft":
		return _to("Would save an email draft for", _first(args, "to"), "Would save an email draft"), {"id": SAMPLE_ID}
	if tool_id.startswith("gcalendar_"):
		verb = tool_id.split("_")[1] if tool_id.count("_") >= 2 else "change"
		return f"Would {verb} a calendar event", {"id": SAMPLE_ID}
	if tool_id in ("frappe_create_record", "frappe_update_record"):
		verb = "create" if tool_id == "frappe_create_record" else "update"
		kind = _first(args, "doctype")
		return (f"Would {verb} a {kind} record" if kind else f"Would {verb} a record"), {"name": SAMPLE_ID}
	if tool_id == "github_create_issue":
		return _to("Would open a GitHub issue in", _first(args, "repo"), "Would open a GitHub issue"), {"number": 1, "html_url": "https://github.com/sample/issue/1"}
	if tool_id == "github_create_pr":
		return _to("Would open a GitHub pull request in", _first(args, "repo"), "Would open a GitHub pull request"), {"number": 1}
	title = label_for(tool_id).lower()
	if effect == SENDS:
		return f"Would send with {title}", {"success": True, "id": SAMPLE_ID}
	return f"Would run {title}", {"success": True, "id": SAMPLE_ID}


def simulated_output(tool_id: str, effect: str, args: Any = None) -> dict:
	"""The output a skipped ``tool.call`` returns. ``effect`` is ``changes`` or ``sends``."""
	args = args if isinstance(args, dict) else {}
	summary, sample = _summary_and_sample(str(tool_id or ""), effect if effect in (CHANGES, SENDS) else CHANGES, args)
	return {"simulated": True, "summary": summary, "note": NOTE, **sample}


def simulated_document(doctype: Any) -> dict:
	"""What a skipped ``doc.create`` hands to later steps (they can use ``name``)."""
	kind = str(doctype or "").strip()
	summary = f"Would create a {kind} record" if kind else "Would create a record"
	return {"simulated": True, "summary": summary, "note": NOTE, "doctype": kind or None, "name": f"(sample) {kind or 'record'}"}


def simulated_code(profile: Any) -> dict:
	"""What a skipped ``code.run`` hands to later steps."""
	return {
		"simulated": True,
		"summary": "Would run your code",
		"note": NOTE,
		"stdout": "",
		"result": None,
		"exit_status": "ok",
		"truncated": False,
	}



def simulated_state(node_type: str, key: Any = None) -> dict:
	"""What a skipped "Save data for later" / "Forget saved data" step hands to later steps."""
	what = str(key).strip() if isinstance(key, str) and key.strip() and not key.strip().startswith("{") else ""
	if node_type == "state.delete":
		return {"simulated": True, "summary": f"Would forget the saved data \"{what}\"" if what else "Would forget saved data", "note": NOTE, "deleted": True}
	return {"simulated": True, "summary": f"Would save data for later as \"{what}\"" if what else "Would save data for later", "note": NOTE, "stored": True}
