# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Immutable value objects shared by every gateway adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class GatewayCredentialField:
	"""One provider configuration field that a gateway administrator supplies."""

	key: str
	label: str
	required: bool = True
	secret: bool = True
	description: str = ""

	def __post_init__(self) -> None:
		if not self.key.strip():
			raise ValueError("Credential field key is required")
		if not self.label.strip():
			raise ValueError("Credential field label is required")


@dataclass(frozen=True, slots=True)
class GatewayCredentialSchema:
	"""Ordered, validated credential schema declared by one adapter."""

	fields: tuple[GatewayCredentialField, ...]

	def __post_init__(self) -> None:
		keys = [field.key for field in self.fields]
		if len(keys) != len(set(keys)):
			raise ValueError("Credential field keys must be unique")

	def missing_required(self, credentials: Mapping[str, Any]) -> tuple[str, ...]:
		"""Return required keys absent or empty from a supplied credential mapping."""
		return tuple(field.key for field in self.fields if field.required and not credentials.get(field.key))


@dataclass(frozen=True, slots=True)
class GatewayCapabilities:
	"""Explicitly declared transport and outbound capabilities of an adapter."""

	ingress_transports: frozenset[str]
	supports_text_reply: bool = True
	supports_thread_reply: bool = False
	supports_media_reply: bool = False
	max_outbound_messages_per_second: float | None = None

	def __post_init__(self) -> None:
		if not self.ingress_transports:
			raise ValueError("At least one ingress transport is required")
		if any(not transport.strip() for transport in self.ingress_transports):
			raise ValueError("Ingress transport names must not be blank")
		if self.max_outbound_messages_per_second is not None and self.max_outbound_messages_per_second <= 0:
			raise ValueError("Outbound message rate limit must be positive")


@dataclass(frozen=True, slots=True)
class GatewayAttachment:
	"""A media/file reference carried by an inbound event or outbound reply.

	Providers identify media either by an opaque ``file_id`` (Telegram, WeCom
	media IDs) that must be resolved via a follow-up provider API call, or by
	a directly fetchable ``url`` (Messenger/WhatsApp/Teams attachment URLs,
	VK doc URLs). At least one of the two should be populated by adapters;
	both are optional here so a partially-known attachment can still be
	surfaced rather than dropped.
	"""

	mime_type: str = ""
	filename: str = ""
	url: str | None = None
	file_id: str | None = None
	# Populated once GW-31-style download logic has saved the content to a
	# Frappe File doctype record; empty for providers/attachments that are
	# only referenced, not yet downloaded.
	file_doc: str | None = None
	kind: str = "file"

	def __post_init__(self) -> None:
		if not self.url and not self.file_id:
			raise ValueError("GatewayAttachment requires a url or a file_id")


@dataclass(frozen=True, slots=True)
class GatewayInboundRequest:
	"""Transport-neutral request data received from a provider."""

	body: bytes
	headers: Mapping[str, str] = field(default_factory=dict)
	query: Mapping[str, str] = field(default_factory=dict)
	method: str = "POST"


@dataclass(frozen=True, slots=True)
class NormalizedGatewayEvent:
	"""A verified provider event in the shape consumed by Huf Gateway ingress."""

	provider_event_id: str
	sender_id: str
	conversation_id: str
	message_text: str
	thread_id: str | None = None
	is_room: bool = False
	mentioned: bool = False
	raw_payload: Mapping[str, Any] = field(default_factory=dict)
	# Optional human-readable sender name (e.g. Telegram @handle or first
	# name). Defaults to "" so adapters that don't populate it -- every
	# adapter but Telegram today -- need no changes; a pending pairing entry
	# then falls back to the bare "Sender <id>" label.
	display_name: str = ""
	# Media/file references carried by this event. Defaults to an empty
	# tuple so adapters that don't populate it need no changes; populated on
	# a best-effort basis per provider payload shape (see GW-30/GW-31).
	attachments: Sequence[GatewayAttachment] = field(default_factory=tuple)

	def __post_init__(self) -> None:
		for name in ("provider_event_id", "sender_id", "conversation_id"):
			if not getattr(self, name).strip():
				raise ValueError(f"{name} is required")


@dataclass(frozen=True, slots=True)
class GatewayReply:
	"""A provider-neutral outbound text reply to a normalized event."""

	conversation_id: str
	text: str
	thread_id: str | None = None
	reply_to_provider_message_id: str | None = None
	# Media to send alongside/instead of text. Adapters that don't support
	# media replies (see GatewayCapabilities.supports_media_reply) ignore
	# this field entirely; it defaults to empty so no existing caller needs
	# changes.
	attachments: Sequence[GatewayAttachment] = field(default_factory=tuple)

	def __post_init__(self) -> None:
		if not self.conversation_id.strip():
			raise ValueError("conversation_id is required")
		if not self.text.strip():
			raise ValueError("Reply text is required")


@dataclass(frozen=True, slots=True)
class OutboundDelivery:
	"""The provider receipt returned after a reply has been accepted."""

	provider_message_id: str
	accepted: bool = True
	provider_response: Mapping[str, Any] = field(default_factory=dict)

	def __post_init__(self) -> None:
		if not self.provider_message_id.strip():
			raise ValueError("provider_message_id is required")
