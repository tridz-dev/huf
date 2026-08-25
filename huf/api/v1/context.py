"""Request context for the Huf public developer API (v1).

Every request handled by the v1 router is resolved into a
`RequestContext` before the handler runs. This gives handlers a single,
stable object to read the authenticated user, auth mode, and request id
from, instead of reaching into `frappe.session` / `frappe.local` directly.
"""

from dataclasses import dataclass, field
from enum import Enum
import uuid

import frappe


class AuthMode(str, Enum):
	"""How the request's principal was resolved.

	Only SESSION is implemented in Phase 1. API_KEY and OAUTH are
	reserved so `huf.api.v1.auth` can add resolvers for them later
	without changing the `RequestContext` shape or call sites.
	"""

	SESSION = "session"
	API_KEY = "api_key"  # noqa: not implemented yet
	OAUTH = "oauth"  # noqa: not implemented yet


@dataclass
class RequestContext:
	"""Resolved identity and metadata for a single v1 API request."""

	user: str
	auth_mode: AuthMode
	request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
	started_at: str = field(default_factory=frappe.utils.now_datetime)
	credential_scopes: list[str] | None = None
	credential_agent_restriction: dict | None = None

	def as_dict(self) -> dict:
		"""Serialize the context for inclusion in logs or debug responses."""
		return {
			"request_id": self.request_id,
			"user": self.user,
			"auth_mode": self.auth_mode.value,
			"started_at": str(self.started_at),
		}
