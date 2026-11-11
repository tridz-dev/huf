"""Idempotent import of a conversation published from Huf Desktop (a local, on-device chat).

Contract: desktop-poc/plans/huf-sync-publish-contract.md

The desktop sends only user/assistant TEXT. Every message carries a stable ``client_message_id`` and the
conversation a stable ``client_conversation_id``; replays and retries (including after a lost response)
are therefore no-ops. The importing user owns the result and all normal Agent Conversation permissions
apply. Nothing here runs an agent or restarts any execution.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now
from frappe.utils.synchronization import filelock

IMPORT_VERSION = 1
MAX_MESSAGES = 100
MAX_CONTENT_CHARS = 100_000
MAX_REQUEST_CHARS = 500_000
MAX_CONVERSATION_MESSAGES = 10_000
MAX_TITLE_CHARS = 140
EXTERNAL_PREFIX = "huf-desktop:"
CHANNEL = "Desktop Import"
_ROLES = {"user": "user", "assistant": "agent"}


@frappe.whitelist()
def import_conversation_capabilities():
	"""Feature detection: the desktop calls this before offering "Publish to Huf"."""
	_require(
		frappe.has_permission("Agent Conversation", "create"), _("Not permitted to create Agent Conversation")
	)
	return {
		"import_conversation": IMPORT_VERSION,
		"max_messages": MAX_MESSAGES,
		"max_content_chars": MAX_CONTENT_CHARS,
		"max_request_chars": MAX_REQUEST_CHARS,
		"delete_imported": 1 if frappe.has_permission("Agent Conversation", "delete") else 0,
	}


@frappe.whitelist()
def import_conversation(
	client_conversation_id: str,
	idempotency_key: str,
	messages,
	title: str | None = None,
	conversation_id: str | None = None,
	agent: str | None = None,
	model: str | None = None,
):
	"""Create (first call) or append to (later calls) the imported copy of one desktop chat."""
	client_conversation_id = _clean_id(client_conversation_id, "client_conversation_id")
	idempotency_key = _clean_id(idempotency_key, "idempotency_key")
	items = _parse_messages(messages)
	external_id = EXTERNAL_PREFIX + client_conversation_id

	with filelock(_lock_name(frappe.session.user, external_id), timeout=30):
		name = _find_conversation(external_id)
		created = False
		if not name:
			# `conversation_id` is only a hint from the desktop; it never selects another user's or a
			# non-imported conversation (an unknown or foreign id simply creates/uses the imported one).
			name = _create_conversation(external_id, title, agent, model)
			created = True

		doc = frappe.get_doc("Agent Conversation", name)
		doc.check_permission("write")
		if doc.owner != frappe.session.user:
			frappe.throw(_("Not permitted"), frappe.PermissionError)

		existing = {
			r.client_message_id
			for r in frappe.get_all(
				"Agent Message",
				filters={
					"conversation": name,
					"client_message_id": ["in", [m["client_message_id"] for m in items]],
				},
				fields=["client_message_id"],
			)
		}
		index = (
			frappe.db.sql(
				"select max(conversation_index) from `tabAgent Message` where conversation=%s", name
			)[0][0]
			or 0
		)
		if index + len(items) - len(existing) > MAX_CONVERSATION_MESSAGES:
			frappe.throw(
				_("Conversation is too large to import (max {0} messages)").format(MAX_CONVERSATION_MESSAGES),
				frappe.ValidationError,
			)
		imported = 0
		message_ids = {}
		for m in items:
			if m["client_message_id"] in existing:
				continue
			index += 1
			msg = frappe.get_doc(
				{
					"doctype": "Agent Message",
					"conversation": name,
					"role": _ROLES[m["role"]],
					"kind": "Message",
					"content": m["content"],
					"user": frappe.session.user if m["role"] == "user" else "Agent",
					"session_id": doc.session_id,
					"conversation_index": index,
					"is_agent_message": 1 if m["role"] == "assistant" else 0,
					"client_message_id": m["client_message_id"],
					"agent": doc.agent,
				}
			)
			msg.insert()
			message_ids[m["client_message_id"]] = msg.name
			imported += 1

		if imported:
			frappe.db.set_value(
				"Agent Conversation",
				name,
				{"total_messages": index, "last_activity": now()},
				update_modified=False,
			)
		return {
			"success": True,
			"conversation_id": name,
			"created": created,
			"imported": imported,
			"skipped": len(items) - imported,
			"message_ids": message_ids,
			"idempotency_key": idempotency_key,
		}


@frappe.whitelist()
def delete_imported_conversation(
	conversation_id: str, client_conversation_id: str, idempotency_key: str | None = None
):
	"""Delete an IMPORTED conversation (only ever called when the user chose it on the desktop).

	Refuses anything that was not created by ``import_conversation`` for this exact client id, so the
	desktop can never delete a normal Huf conversation through this method. Idempotent.
	"""
	client_conversation_id = _clean_id(client_conversation_id, "client_conversation_id")
	external_id = EXTERNAL_PREFIX + client_conversation_id
	with filelock(_lock_name(frappe.session.user, external_id), timeout=30):
		name = _find_conversation(external_id)
		if not name or name != conversation_id:
			return {"success": True, "deleted": False}
		doc = frappe.get_doc("Agent Conversation", name)
		doc.check_permission("delete")
		# Agent Message links to the conversation, so delete_doc would raise LinkExistsError while any
		# message remains. Permission was checked above; remove the messages, then the conversation.
		frappe.db.delete("Agent Message", {"conversation": name})
		frappe.delete_doc("Agent Conversation", name, ignore_permissions=True)
		return {"success": True, "deleted": True}


# ── helpers ────────────────────────────────────────────────────────────────


def _require(ok, msg):
	if not ok:
		frappe.throw(msg, frappe.PermissionError)


def _clean_id(value, field):
	if (
		not isinstance(value, str)
		or not (1 <= len(value) <= 64)
		or not all(c.isalnum() or c in "-_:." for c in value)
	):
		frappe.throw(_("Invalid {0}").format(field), frappe.ValidationError)
	return value


def _parse_messages(raw):
	try:
		items = json.loads(raw) if isinstance(raw, str) else raw
	except ValueError:
		frappe.throw(_("messages must be valid JSON"), frappe.ValidationError)
	if not isinstance(items, list) or not items:
		frappe.throw(_("messages must be a non-empty list"), frappe.ValidationError)
	if len(items) > MAX_MESSAGES:
		frappe.throw(
			_("Too many messages in one request (max {0})").format(MAX_MESSAGES), frappe.ValidationError
		)
	seen, out, total = set(), [], 0
	for m in items:
		if not isinstance(m, dict) or m.get("role") not in _ROLES:
			frappe.throw(_("Only user and assistant messages can be imported"), frappe.ValidationError)
		content = m.get("content")
		if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT_CHARS:
			frappe.throw(_("Invalid message content"), frappe.ValidationError)
		total += len(content)
		if total > MAX_REQUEST_CHARS:
			frappe.throw(
				_("Request too large (max {0} characters)").format(MAX_REQUEST_CHARS), frappe.ValidationError
			)
		cid = _clean_id(m.get("client_message_id"), "client_message_id")
		if cid in seen:
			frappe.throw(_("Duplicate client_message_id in request"), frappe.ValidationError)
		seen.add(cid)
		out.append({"client_message_id": cid, "role": m["role"], "content": content})
	return out


def _lock_name(user, external_id):
	return "huf_import_" + hashlib.sha256(f"{user}|{external_id}".encode()).hexdigest()


def _find_conversation(external_id):
	# Scoped to the calling user: two accounts never see or merge each other's imports.
	return frappe.db.get_value(
		"Agent Conversation",
		{"external_id": external_id, "owner": frappe.session.user, "channel": CHANNEL},
		"name",
	)


def _create_conversation(external_id, title, agent, model):
	if not frappe.has_permission("Agent Conversation", "create"):
		frappe.throw(_("Not permitted to create Agent Conversation"), frappe.PermissionError)
	title = title.strip() if isinstance(title, str) else ""
	if not (isinstance(agent, str) and agent and frappe.has_permission("Agent", "read", agent)):
		agent = None
	doc = frappe.get_doc(
		{
			"doctype": "Agent Conversation",
			"title": (title or _("Imported chat"))[:MAX_TITLE_CHARS],
			"agent": agent,
			"session_id": "desktop-import-" + frappe.generate_hash(length=10),
			"channel": CHANNEL,
			"external_id": external_id,
			"created_at": now(),
			"last_activity": now(),
			"is_active": 1,
		}
	)
	doc.insert()
	return doc.name
