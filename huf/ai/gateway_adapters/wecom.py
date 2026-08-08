# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WeCom self-built-application callback and messaging adapter."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
import xml.etree.ElementTree as element_tree
from collections.abc import Callable, Mapping
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
)


WECOM_GET_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_SEND_MESSAGE_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"


def _requests_get(url: str, *, params: Mapping[str, str], timeout: int) -> Any:
	"""Lazily import requests so this package has no import-time HTTP dependency."""
	import requests

	return requests.get(url, params=params, timeout=timeout)


def _requests_post(url: str, *, params: Mapping[str, str], json: Mapping[str, Any], timeout: int) -> Any:
	"""Lazily import requests so this package has no import-time HTTP dependency."""
	import requests

	return requests.post(url, params=params, json=json, timeout=timeout)


class WeComGatewayAdapter(GatewayAdapter):
	"""Fail-closed WeCom encrypted callback adapter for a self-built app."""

	provider_id = "wecom"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("corp_id", "Corporation ID", secret=False),
			GatewayCredentialField("agent_id", "Application Agent ID", secret=False),
			GatewayCredentialField("corp_secret", "Application Secret"),
			GatewayCredentialField("callback_token", "Callback Token"),
			GatewayCredentialField("encoding_aes_key", "Callback EncodingAESKey"),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=False,
		max_outbound_messages_per_second=0.5,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_get: Callable[..., Any] = _requests_get,
		http_post: Callable[..., Any] = _requests_post,
		clock: Callable[[], float] = time.monotonic,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"WeCom adapter is missing required credentials: {', '.join(missing)}")
		self._corp_id = credentials["corp_id"]
		self._agent_id = credentials["agent_id"]
		self._corp_secret = credentials["corp_secret"]
		self._callback_token = credentials["callback_token"]
		self._aes_key = self._decode_aes_key(credentials["encoding_aes_key"])
		self._http_get = http_get
		self._http_post = http_post
		self._clock = clock
		self._access_token: str | None = None
		self._access_token_expires_at = 0.0

	def verify_url(self, request: GatewayInboundRequest) -> str:
		"""Verify a WeCom GET callback challenge and return its plaintext echo."""
		encrypted = request.query.get("echostr", "")
		if not encrypted or not self._valid_signature(request.query, encrypted):
			raise ValueError("WeCom callback URL verification failed")
		return self._decrypt(encrypted).decode("utf-8")

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Return true only for signed, decryptable callbacks addressed to this corp."""
		try:
			encrypted = self._encrypted_body(request.body)
			if not encrypted or not self._valid_signature(request.query, encrypted):
				return False
			self._decrypt(encrypted)
			return True
		except (ValueError, UnicodeDecodeError, element_tree.ParseError):
			return False

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Normalize a verified WeCom text callback; reject unsupported events."""
		if not self.verify_inbound(request):
			raise ValueError("WeCom callback was not verified")
		xml_body = self._decrypt(self._encrypted_body(request.body) or "")
		root = element_tree.fromstring(xml_body)
		if self._xml_text(root, "MsgType") != "text":
			raise ValueError("WeCom callback is not a text message")
		message_id = self._xml_text(root, "MsgId")
		sender_id = self._xml_text(root, "FromUserName")
		if not message_id or not sender_id:
			raise ValueError("WeCom text callback is missing message or sender identifier")
		return NormalizedGatewayEvent(
			provider_event_id=message_id,
			sender_id=sender_id,
			conversation_id=sender_id,
			message_text=self._xml_text(root, "Content") or "",
			raw_payload={"xml": xml_body.decode("utf-8")},
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send an application text message to the reply's WeCom recipient."""
		access_token = self._get_access_token()
		payload = {
			"touser": reply.conversation_id,
			"msgtype": "text",
			"agentid": self._agent_id,
			"text": {"content": reply.text},
		}
		response = self._http_post(
			WECOM_SEND_MESSAGE_URL,
			params={"access_token": access_token},
			json=payload,
			timeout=10,
		)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping):
			raise ValueError("WeCom message send returned an invalid response")
		if body.get("errcode", 0) != 0:
			raise ValueError(f"WeCom message send failed with errcode {body.get('errcode')}")
		message_id = body.get("msgid")
		if not message_id:
			raise ValueError("WeCom message send response did not include a message id")
		return OutboundDelivery(str(message_id), provider_response=body)

	def _get_access_token(self) -> str:
		if self._access_token and self._clock() < self._access_token_expires_at:
			return self._access_token
		response = self._http_get(
			WECOM_GET_TOKEN_URL,
			params={"corpid": self._corp_id, "corpsecret": self._corp_secret},
			timeout=10,
		)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping) or body.get("errcode", 0) != 0 or not body.get("access_token"):
			raise ValueError("WeCom access token request failed")
		self._access_token = str(body["access_token"])
		expires_in = int(body.get("expires_in") or 0)
		self._access_token_expires_at = self._clock() + max(0, expires_in - 60)
		return self._access_token

	def _valid_signature(self, query: Mapping[str, str], encrypted: str) -> bool:
		timestamp = query.get("timestamp", "")
		nonce = query.get("nonce", "")
		provided = query.get("msg_signature", "")
		if not timestamp or not nonce or not provided:
			return False
		candidate = hashlib.sha1("".join(sorted((self._callback_token, timestamp, nonce, encrypted))).encode()).hexdigest()
		return hmac.compare_digest(candidate, provided)

	def _decrypt(self, encrypted: str) -> bytes:
		try:
			ciphertext = base64.b64decode(encrypted)
		except Exception as exc:
			raise ValueError("WeCom callback ciphertext is invalid") from exc
		decryptor = Cipher(algorithms.AES(self._aes_key), modes.CBC(self._aes_key[:16])).decryptor()
		plain = decryptor.update(ciphertext) + decryptor.finalize()
		if not plain:
			raise ValueError("WeCom callback plaintext is empty")
		padding = plain[-1]
		if padding < 1 or padding > 32 or plain[-padding:] != bytes([padding]) * padding:
			raise ValueError("WeCom callback padding is invalid")
		content = plain[:-padding]
		if len(content) < 20:
			raise ValueError("WeCom callback plaintext is malformed")
		xml_length = struct.unpack("!I", content[16:20])[0]
		xml_end = 20 + xml_length
		if xml_end > len(content):
			raise ValueError("WeCom callback XML length is invalid")
		receive_id = content[xml_end:].decode("utf-8")
		if not hmac.compare_digest(receive_id, self._corp_id):
			raise ValueError("WeCom callback receive-id does not match corporation")
		return content[20:xml_end]

	@staticmethod
	def _decode_aes_key(value: str) -> bytes:
		try:
			key = base64.b64decode(f"{value}=")
		except Exception as exc:
			raise ValueError("WeCom EncodingAESKey is invalid") from exc
		if len(key) != 32:
			raise ValueError("WeCom EncodingAESKey must decode to 32 bytes")
		return key

	@staticmethod
	def _encrypted_body(body: bytes) -> str | None:
		root = element_tree.fromstring(body)
		return WeComGatewayAdapter._xml_text(root, "Encrypt")

	@staticmethod
	def _xml_text(root: element_tree.Element, tag: str) -> str | None:
		element = root.find(tag)
		return element.text if element is not None else None
