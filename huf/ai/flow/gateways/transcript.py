"""Opt-in voice transcript for gateway triggers (Q7). Runs inside the enqueued flow job, never in the webhook request.

Only a flow whose matching trigger lists ``voice`` or ``audio`` in ``message_kinds`` asks for one. The text a stranger
spoke is customer-provided: it is returned wrapped as untrusted so an AI step treats it as data.
"""

from __future__ import annotations

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES

VOICE_KINDS = ("voice", "audio")


def trigger_wants_transcript(node: dict) -> bool:
	"""True when this gateway trigger node's ``message_kinds`` filter includes a voice kind."""
	if not isinstance(node, dict) or node.get("type") not in GATEWAY_NODE_TYPES:
		return False
	for item in (node.get("config") or {}).get("params") or []:
		if isinstance(item, dict) and item.get("key") == "message_kinds" and isinstance(item.get("value"), list):
			return any(kind in VOICE_KINDS for kind in item["value"])
	return False


def transcript_for_attachments(attachments, agent_name: str | None, language: str | None = None) -> str:
	"""Untrusted-wrapped transcript of the first audio file, or ``""`` (no agent, no file, or the speech service failed)."""
	if not agent_name or not attachments:
		return ""
	from huf.ai import audio_service
	from huf.ai.gateways.safety import wrap_untrusted

	for file_id in list(attachments)[:1]:
		try:
			result = audio_service.transcribe_audio_file(file_id=file_id, agent_name=agent_name, language=language or None)
		except Exception:
			return ""
		result = result if isinstance(result, dict) else {}
		text = result.get("transcript") or result.get("text")
		if text:
			return wrap_untrusted(text, "voice note")
	return ""
