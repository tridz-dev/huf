"""Short-lived, user-bound secret collection for Hub Orchestrator.

The request record contains only routing metadata. The secret is sent directly
to this endpoint and assigned to an encrypted Password field; it is never
placed in the agent conversation or in the request cache.
"""

import json
import secrets

import frappe
from frappe import _

from huf.ai.tools.builder import _require_builder_capability, _require_doc_permission


_REQUEST_PREFIX = "huf:hub-secret-request:"
_REQUEST_LOCK_PREFIX = "huf:hub-secret-request-lock:"
_REQUEST_TTL_SECONDS = 10 * 60
_MAX_SECRET_LENGTH = 16_384
_TARGET_TYPES = {"provider_api_key", "integration_credential"}


def _parse_target(target) -> dict:
	if isinstance(target, str):
		try:
			target = json.loads(target)
		except (TypeError, ValueError):
			frappe.throw(_("'secure_target' must be an object or JSON-encoded object."))
	if not isinstance(target, dict):
		frappe.throw(_("'secure_target' must be an object or JSON-encoded object."))

	target_type = str(target.get("type") or "").strip()
	if target_type not in _TARGET_TYPES:
		frappe.throw(_("'secure_target.type' is not an approved Hub target."))

	if target_type == "provider_api_key":
		provider_name = str(target.get("provider_name") or "").strip()
		if not provider_name or not frappe.db.exists("AI Provider", provider_name):
			frappe.throw(_("The selected AI Provider does not exist."))
		return {"type": target_type, "provider_name": provider_name}

	settings_name = str(target.get("integration_settings") or "").strip()
	credential_key = str(target.get("credential_key") or "").strip()
	if not settings_name or not credential_key:
		frappe.throw(
			_("Integration secret requests need integration_settings and credential_key.")
		)
	if not frappe.db.exists("Integration Settings", settings_name):
		frappe.throw(_("The selected Integration Settings record does not exist."))

	settings = frappe.get_doc("Integration Settings", settings_name)
	service = frappe.get_doc("Integration Service", settings.service)
	try:
		schema = service.required_credentials or "[]"
		schema = json.loads(schema) if isinstance(schema, str) else schema
	except (TypeError, ValueError):
		frappe.throw(_("The integration has an invalid credential schema."))

	allowed_keys = {
		str(item.get("key") or "").strip()
		for item in (schema or [])
		if isinstance(item, dict)
	}
	if credential_key not in allowed_keys:
		frappe.throw(_("That credential key is not approved for this integration service."))

	return {
		"type": target_type,
		"integration_settings": settings_name,
		"credential_key": credential_key,
	}


def _request_key(request_id: str) -> str:
	return f"{_REQUEST_PREFIX}{request_id}"


def _request_lock_key(request_id: str) -> str:
	return f"{_REQUEST_LOCK_PREFIX}{request_id}"


def _target_label(target: dict) -> str:
	if target["type"] == "provider_api_key":
		return f"API key for {target['provider_name']}"
	return f"{target['credential_key']} for {target['integration_settings']}"


def create_secret_request(target, conversation_id=None, agent_name=None) -> dict:
	"""Create a safe request descriptor for an interactive Hub password card."""
	_require_builder_capability()
	clean_target = _parse_target(target)
	request_id = secrets.token_urlsafe(24)
	frappe.cache().set_value(
		_request_key(request_id),
		{
			"user": frappe.session.user,
			"conversation_id": conversation_id,
			"agent_name": agent_name,
			"target": clean_target,
		},
		expires_in_sec=_REQUEST_TTL_SECONDS,
	)
	return {
		"request_id": request_id,
		"conversation_id": conversation_id,
		"target": clean_target,
		"target_label": _target_label(clean_target),
		"expires_in": _REQUEST_TTL_SECONDS,
	}


def _load_request(request_id: str) -> dict:
	request_id = str(request_id or "").strip()
	if not request_id or len(request_id) > 256:
		frappe.throw(_("This secret request is invalid or expired."))
	record = frappe.cache().get_value(_request_key(request_id))
	if not isinstance(record, dict):
		frappe.throw(_("This secret request is invalid or expired."))
	if record.get("user") != frappe.session.user:
		frappe.throw(_("This secret request belongs to another user."), frappe.PermissionError)
	return record


def _save_provider_key(target: dict, secret: str) -> None:
	provider = frappe.get_doc("AI Provider", target["provider_name"])
	_require_doc_permission("AI Provider", "write", provider.name)
	provider.api_key = secret
	provider.save()


def _save_integration_credential(target: dict, secret: str) -> None:
	settings = frappe.get_doc("Integration Settings", target["integration_settings"])
	_require_doc_permission("Integration Settings", "write", settings.name)
	key = target["credential_key"]
	for credential in settings.credentials or []:
		if credential.key == key:
			credential.value = secret
			break
	else:
		settings.append("credentials", {"key": key, "value": secret})
	settings.save()


@frappe.whitelist()
def submit_hub_secret(request_id: str, secret: str, conversation_id=None) -> dict:
	"""Consume a Hub secret request and write the secret to its approved target."""
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be signed in to configure a secret."), frappe.PermissionError)

	_require_builder_capability()
	record = _load_request(request_id)
	stored_conversation = record.get("conversation_id")
	if stored_conversation and conversation_id != stored_conversation:
		frappe.throw(_("This secret request is for a different conversation."), frappe.PermissionError)

	secret = str(secret or "")
	if not secret.strip():
		frappe.throw(_("A non-empty secret is required."))
	if len(secret) > _MAX_SECRET_LENGTH:
		frappe.throw(_("The secret is too long."))

	cache = frappe.cache()
	if not cache.set(_request_lock_key(request_id), 1, ex=60, nx=True):
		frappe.throw(_("This secret request is already being submitted."))
	try:
		target = record["target"]
		if target["type"] == "provider_api_key":
			_save_provider_key(target, secret)
		else:
			_save_integration_credential(target, secret)
		# Consume only after the encrypted field has been written, so a transient
		# save failure leaves the short-lived request retryable.
		cache.delete_value(_request_key(request_id))
	finally:
		cache.delete(_request_lock_key(request_id))

	return {"configured": True, "target": target, "target_label": _target_label(target)}
