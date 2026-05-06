"""
Shared utilities for media tool handlers (image, audio, OCR).

Extracts common boilerplate that was repeated across image generation,
audio generation, OCR, and audio transcription handlers.
"""

import frappe
from frappe.utils.file_manager import save_file


def get_agent_provider_config(agent_name: str) -> tuple:
	"""
	Load agent doc, provider doc, and decrypted API key.

	Args:
		agent_name: Name of the Agent document

	Returns:
		tuple: (agent_doc, provider_doc, api_key)

	Raises:
		ValueError: If agent not found or API key missing.
	"""
	if not agent_name:
		raise ValueError("Agent name not found in context")

	agent_doc = frappe.get_doc("Agent", agent_name)
	provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
	api_key = provider_doc.get_password("api_key")

	if not api_key:
		raise ValueError("API key not configured for provider")

	return agent_doc, provider_doc, api_key


def get_next_conversation_index(conversation_id: str) -> int:
	"""Get the next sequential conversation_index for a conversation."""
	try:
		last_index = frappe.db.sql(
			"""
			SELECT MAX(conversation_index) as last_index
			FROM `tabAgent Message`
			WHERE conversation = %s
		""",
			(conversation_id,),
			as_dict=1,
		)

		return (
			last_index[0].last_index if last_index and last_index[0].last_index is not None else 0
		) + 1
	except Exception:
		return 1


def create_agent_message(
	conversation_id: str,
	agent_name: str,
	agent_doc,
	kind: str,
	content: str,
	conversation_index: int,
	agent_run_id: str = None,
	**extra_fields,
):
	"""
	Create an Agent Message document.

	Args:
		conversation_id: Conversation ID
		agent_name: Agent name
		agent_doc: Loaded Agent document
		kind: Message kind (Image, Audio, Message)
		content: Message content text
		conversation_index: Sequential index in conversation
		agent_run_id: Optional agent run ID
		**extra_fields: Additional fields to set on the message

	Returns:
		frappe.Document or None on failure (logs error)
	"""
	try:
		doc_data = {
			"doctype": "Agent Message",
			"conversation": conversation_id,
			"role": "agent",
			"content": content,
			"kind": kind,
			"agent": agent_name,
			"provider": agent_doc.provider,
			"model": agent_doc.model,
			"agent_run": agent_run_id,
			"conversation_index": conversation_index,
			"is_agent_message": 1,
			"user": "Agent",
		}
		doc_data.update(extra_fields)

		message_doc = frappe.get_doc(doc_data)
		message_doc.insert(ignore_permissions=True)
		return message_doc
	except Exception as e:
		frappe.log_error(
			title=f"{kind} Message Creation",
			message=f"Error creating Agent Message for {kind.lower()}: {str(e)}",
		)
		return None


def save_media_file(
	filename: str,
	content: bytes,
	message_doc=None,
	conversation_id: str = None,
	field_name: str = None,
	is_private: bool = False,
) -> tuple:
	"""
	Save a media file, attach to message or conversation.

	Args:
		filename: Name for the file
		content: File content bytes
		message_doc: Agent Message doc to attach to (preferred)
		conversation_id: Fallback conversation ID
		field_name: Optional Attach field name (e.g., "generated_image")
		is_private: Whether file should be private

	Returns:
		tuple: (file_url, file_id)
	"""
	if message_doc:
		saved_file = save_file(
			filename,
			content,
			"Agent Message",
			message_doc.name,
			is_private=is_private,
			df=field_name,
		)
	else:
		saved_file = save_file(
			filename,
			content,
			"Agent Conversation",
			conversation_id or "Unknown",
			is_private=is_private,
		)

	file_url = getattr(saved_file, "file_url", None)
	file_id = getattr(saved_file, "name", None)

	if not file_url:
		file_url = f"/files/{getattr(saved_file, 'file_name', filename)}"

	return file_url, file_id


def emit_message_event(
	conversation_id: str,
	message_doc,
	kind: str,
	extra_data: dict = None,
):
	"""
	Publish a realtime socket event for a new agent message.

	Args:
		conversation_id: Conversation ID
		message_doc: Agent Message document
		kind: Message kind (Image, Audio, Message)
		extra_data: Additional data to include in the event
	"""
	try:
		event_data = {
			"type": "new_agent_message",
			"conversation_id": conversation_id,
			"message_id": message_doc.name,
			"kind": kind,
			"content": message_doc.content,
			"conversation_index": message_doc.conversation_index,
		}
		if extra_data:
			event_data.update(extra_data)

		frappe.publish_realtime(
			event=f"conversation:{conversation_id}",
			message=event_data,
			user=frappe.session.user,
			after_commit=False,
		)
	except Exception as e:
		frappe.log_error(
			title=f"{kind} Socket Event",
			message=f"Error emitting new_agent_message socket event: {str(e)}",
		)


def update_conversation_total_messages(conversation_id: str, index: int):
	"""Update the conversation's total_messages and last_activity."""
	try:
		frappe.db.sql(
			"""
			UPDATE `tabAgent Conversation`
			SET total_messages = %s, last_activity = NOW()
			WHERE name = %s
		""",
			(index, conversation_id),
		)
	except Exception as e:
		frappe.log_error(
			title="Conversation Update",
			message=f"Error updating conversation total_messages: {str(e)}",
		)
