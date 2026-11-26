# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""Per-user conversation routing for Dedicated Automations.

When the Automation's agent has ``persist_user_history`` on and the
Automation's ``conversation_mode`` is ``Dedicated``, each run identity gets
its own conversation instead of the single ``automation.conversation`` link.

The identity is the one ``run_automation`` already resolved and switched to
(``initiating_user or automation.run_as_user``, else the session user), so at
call time it is simply ``frappe.session.user``:

* Doc Event: the user who made the change (captured at enqueue time).
* App Event / "Run now": the passed ``initiating_user``.
* Schedule / Webhook: ``run_as_user``, else the session user of that job.

A Guest or empty identity never reads or writes a stored conversation.
"""

from __future__ import annotations

from uuid import uuid4

import frappe

CHANNEL_ID = "automation"
_ANONYMOUS = ("", "Guest")


def is_active(automation) -> bool:
	"""True when this run should be keyed per user."""
	if automation.get("conversation_mode") != "Dedicated" or not automation.get("agent"):
		return False
	return bool(frappe.db.get_value("Agent", automation.agent, "persist_user_history"))


def resolve_routing(automation):
	"""Return ``(conversation_id, channel_id, external_id, skip_user_message)``.

	The conversation is looked up by ``external_id`` (which embeds the run
	identity), so no ``conversation_id`` is passed and nothing is stored on
	the Automation.
	"""
	user = frappe.session.user
	if not user or user in _ANONYMOUS:
		return None, CHANNEL_ID, f"automation-new:{automation.name}:{uuid4().hex[:12]}", False
	return None, CHANNEL_ID, f"automation:{automation.name}:user:{user}", False
