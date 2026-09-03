# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""
Huf API Key controller.

A Huf API Key lets an external developer authenticate as a Huf user with a
REDUCED, explicitly-scoped set of capabilities -- never elevated beyond
whatever the owning user could already do. Only the SHA-256 hash of the
secret is ever persisted; the raw secret is generated and returned exactly
once, at creation time, and is unrecoverable after that.

Hashing approach
-----------------
API keys differ from user passwords: they are already high-entropy,
machine-generated random tokens (32 bytes of `secrets.token_urlsafe`
output), not low-entropy human-chosen strings. There is therefore no need
for a slow, salted KDF (bcrypt/argon2/scrypt) whose whole purpose is to
resist offline dictionary/brute-force attacks against weak secrets -- a
plain, fast SHA-256 digest, compared in constant time, is the standard
approach used by GitHub, Stripe, and most API-key systems for this reason.
`frappe.utils.password` was checked for a reusable primitive; the helpers
there (`update_password` / `check_password` / `get_decrypted_password`)
are wired specifically to the `User` doctype's Auth table and to a
*reversible* Fernet-based encryption for "Password" fieldtype values --
neither fits "store only a one-way hash of an arbitrary secret string" --
so a hand-rolled (but standard-library, no hand-rolled crypto) SHA-256 +
`hmac.compare_digest` scheme is used instead.
"""

import hashlib
import hmac
import json
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from huf.permissions import has_capability

KEY_PREFIX = "huf_sk_"

# V1 scope catalogue. Deliberately a small, hand-curated subset of the
# internal Huf capability catalogue (see huf/permissions.py) -- API keys
# must never expose the full internal capability surface.
ALLOWED_SCOPES = frozenset(
	[
		"agents:read",
		"agents:run",
		"conversations:read",
		"conversations:write",
		"files:read",
		"files:write",
		"voice:use",
		"ocr:use",
	]
)

AGENT_RESTRICTION_MODES = frozenset(["all", "selected"])


def _hash_secret(raw_secret: str) -> str:
	"""One-way SHA-256 hex digest of a raw API key secret."""
	return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str]:
	"""Generate a new (key_id, raw_secret) pair.

	`raw_secret` is the only time the plaintext secret exists; callers must
	return it to the user once and never persist it. `key_id` is a
	non-secret, human-visible identifier used to look the key up later.
	"""
	raw_secret = KEY_PREFIX + secrets.token_urlsafe(32)
	key_id = KEY_PREFIX + secrets.token_hex(8)
	return key_id, raw_secret


class HufAPIKey(Document):
	def before_insert(self):
		# `_raw_secret` is a transient attribute set by create_api_key();
		# it is never a real field and is never persisted by Frappe.
		raw_secret = getattr(self, "_raw_secret", None)
		if not raw_secret:
			frappe.throw(_("An API key cannot be created without a generated secret."))

		self.hashed_secret = _hash_secret(raw_secret)
		if not self.status:
			self.status = "Active"

	def validate(self):
		self._validate_scopes()
		self._validate_agent_restriction()

	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return True

		if permission_type in ("create", "write", "save", "delete", "read"):
			if has_capability(user, "developer.keys.manage"):
				# Still limited to the caller's own keys outside System Manager.
				return self.is_new() or self.owner == user
			return False

		return True

	def _validate_scopes(self):
		scopes = self._get_scopes_list()
		invalid = sorted(set(scopes) - ALLOWED_SCOPES)
		if invalid:
			frappe.throw(_("Unknown scope(s): {0}").format(", ".join(invalid)))

	def _validate_agent_restriction(self):
		if self.agent_restriction_mode not in AGENT_RESTRICTION_MODES:
			frappe.throw(_("Invalid agent restriction mode: {0}").format(self.agent_restriction_mode))

		if self.agent_restriction_mode == "selected":
			agents = self._get_restricted_agents_list()
			if not agents:
				frappe.throw(_("At least one agent must be selected when restricting by agent."))
			for agent_name in agents:
				if not frappe.db.exists("Agent", agent_name):
					frappe.throw(_("Unknown agent: {0}").format(agent_name))

	def _get_scopes_list(self) -> list[str]:
		return _parse_json_list(self.scopes)

	def _get_restricted_agents_list(self) -> list[str]:
		return _parse_json_list(self.restricted_agents)


def _parse_json_list(value) -> list[str]:
	if not value:
		return []
	try:
		parsed = json.loads(value)
	except (TypeError, ValueError):
		frappe.throw(_("Expected a JSON list."))
	if not isinstance(parsed, list):
		frappe.throw(_("Expected a JSON list."))
	return parsed


def verify_key(raw_key: str) -> "HufAPIKey | None":
	"""Verify a raw API key secret presented by a caller.

	Looks up candidate `Huf API Key` records by `hashed_secret` (a
	deterministic function of the secret, so the lookup itself is exact --
	no need to scan every row) and then re-confirms the match with a
	constant-time comparison, so no timing signal about "how much of the
	hash matched" ever leaks. Returns `None` (never raises) for any
	invalid, revoked, or expired key so callers can treat "not
	authenticated" uniformly. On success, updates `last_used_at` and
	returns the doc.
	"""
	if not raw_key or not raw_key.startswith(KEY_PREFIX):
		return None

	candidate_hash = _hash_secret(raw_key)

	name = frappe.db.get_value("Huf API Key", {"hashed_secret": candidate_hash}, "name")
	if not name:
		return None

	doc = frappe.get_doc("Huf API Key", name)

	if not hmac.compare_digest(doc.hashed_secret or "", candidate_hash):
		return None

	if doc.status != "Active":
		return None

	if doc.expires_at and frappe.utils.now_datetime() > frappe.utils.get_datetime(doc.expires_at):
		return None

	doc.db_set("last_used_at", now_datetime(), update_modified=False)
	return doc


def _require_manage_capability() -> None:
	if not has_capability(frappe.session.user, "developer.keys.manage"):
		frappe.throw(
			_("You don't have permission to manage developer API keys."),
			frappe.PermissionError,
		)


def _serialize_key(doc: "HufAPIKey") -> dict:
	"""Public-safe representation of a key -- never includes hashed_secret."""
	return {
		"key_id": doc.key_id,
		"label": doc.label,
		"status": doc.status,
		"scopes": doc._get_scopes_list(),
		"agent_restriction_mode": doc.agent_restriction_mode,
		"restricted_agents": doc._get_restricted_agents_list(),
		"expires_at": doc.expires_at,
		"last_used_at": doc.last_used_at,
		"creation": doc.creation,
	}


@frappe.whitelist()
def create_api_key(
	label: str,
	scopes: list | str,
	agent_restriction_mode: str = "all",
	restricted_agents: list | str | None = None,
	expires_at: str | None = None,
) -> dict:
	"""Create a new Huf API Key for the calling user.

	Returns the raw secret ONCE; it is never retrievable again after this
	call returns. Requires the `developer.keys.manage` capability.
	"""
	_require_manage_capability()

	if isinstance(scopes, str):
		scopes = _parse_json_list(scopes)
	if isinstance(restricted_agents, str):
		restricted_agents = _parse_json_list(restricted_agents)

	key_id, raw_secret = generate_key()

	doc = frappe.new_doc("Huf API Key")
	doc.key_id = key_id
	doc.label = label
	doc.scopes = json.dumps(scopes or [])
	doc.agent_restriction_mode = agent_restriction_mode
	doc.restricted_agents = json.dumps(restricted_agents or [])
	doc.expires_at = expires_at
	doc.status = "Active"
	doc._raw_secret = raw_secret
	doc.insert()

	result = _serialize_key(doc)
	result["raw_secret"] = raw_secret
	return result


@frappe.whitelist()
def revoke_api_key(key_id: str) -> dict:
	"""Revoke a Huf API Key. Requires `developer.keys.manage`; a non-System-Manager
	caller may only revoke their own keys (enforced via has_permission on save)."""
	_require_manage_capability()

	doc = frappe.get_doc("Huf API Key", key_id)
	if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("You can only revoke your own API keys."), frappe.PermissionError)

	doc.status = "Revoked"
	doc.save()
	return {"key_id": doc.key_id, "status": doc.status}


@frappe.whitelist()
def list_api_keys() -> list[dict]:
	"""List the calling user's own API keys. Never includes hashed_secret."""
	_require_manage_capability()

	names = frappe.get_all(
		"Huf API Key",
		filters={"owner": frappe.session.user},
		pluck="name",
		order_by="creation desc",
	)
	return [_serialize_key(frappe.get_doc("Huf API Key", name)) for name in names]


def get_api_key_permission_conditions(user):
	"""
	Restrict Huf API Key list to keys owned by the user.

	API keys are inherently per-user; no capability carve-out is needed.
	"""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None

	# Only own keys
	return f"`tabHuf API Key`.owner = {frappe.db.escape(user)}"
