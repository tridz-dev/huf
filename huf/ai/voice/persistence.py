"""Persistence helpers for the realtime voice sidecar.

Deliberately separate from huf.ai.conversation_manager's own call sites
(the ElevenLabs webhook has its own inline ConversationManager usage and
is not touched here) - this module exists specifically for the realtime
sidecar process (huf.ai.voice.sidecar.app), which runs outside a normal
Frappe request/response cycle and needs a narrow, defensive surface.
"""

from __future__ import annotations

import frappe

from huf.ai.conversation_manager import ConversationManager


def get_or_create_voice_conversation(agent_name: str, conversation_id: str | None):
	"""Resolve the Agent Conversation a realtime voice session should write into.

	If conversation_id is given, joins that existing conversation (subject to
	ConversationManager's own access rules). Otherwise starts a fresh
	conversation on a dedicated "realtime_voice" channel, keyed by a random
	session-scoped external_id so concurrent unrelated calls to the same
	agent don't collide into one conversation.
	"""
	cm = ConversationManager(
		agent_name=agent_name,
		channel="realtime_voice",
		external_id=conversation_id or frappe.generate_hash(length=16),
	)
	return cm, cm.get_or_create_conversation(
		title=f"Voice Call: {agent_name}", conversation_id=conversation_id
	)


def record_voice_turn(
	cm: ConversationManager, conversation, agent_name: str, role: str, content: str
) -> None:
	"""Persist one realtime voice turn as a normal Agent Message.

	role is "agent" or "user". Silently no-ops on blank content (a realtime
	transcript event can legitimately carry empty text, e.g. a barge-in with
	no words yet transcribed).
	"""
	if not content or not content.strip():
		return
	cm.add_message(
		conversation=conversation,
		role=role,
		content=content,
		provider="",
		model="",
		agent=agent_name,
		kind="Audio",
	)
