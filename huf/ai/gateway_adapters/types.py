# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Immutable value objects shared by every gateway adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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
