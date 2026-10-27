"""Frozen contract for the Microsoft Teams gateway (P0, ``teams-p0/1``).

Later work packages (T1..T15) code against the names in this module and must
not change them without a contract version bump. Nothing here performs I/O.

Module ownership (functions each package must provide; see ``PROTOCOLS``):

- ``teams_auth.verify_bearer``            (T1)
- ``teams_auth.get_bot_token``            (T2; may live in ``teams_api``)
- ``teams_outbox.enqueue``                (T6)
- ``teams_refs.upsert_reference``         (T4)
- ``teams_identity.resolve_user``         (T7)

Identity mapping (v2 decision): Teams tenant id -> ``Gateway Identity Link.team_id``,
Entra object id (``aadObjectId``) -> ``external_id``, provider ``"Microsoft Teams"``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

CONTRACT_VERSION = "teams-p0/1"

PROVIDER_ID = "microsoft_teams"
PROVIDER_LABEL = "Microsoft Teams"  # Gateway.provider value

# Bot Framework endpoints (commercial cloud only in P0).
OPENID_METADATA_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
BOT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
BOT_TOKEN_SCOPE = "https://api.botframework.com/.default"
BOT_ISSUER = "https://api.botframework.com"
ENTRA_ISSUER_TEMPLATES = (
	"https://login.microsoftonline.com/{tenant_id}/v2.0",
	"https://sts.windows.net/{tenant_id}/",
)
CLOCK_SKEW_SECONDS = 300
JWKS_CACHE_SECONDS = 24 * 3600


class TeamsActivityKind(str, enum.Enum):
	"""``raw_payload["huf_kind"]`` values written by the adapter's normalize step."""

	MESSAGE = "message"
	CARD_ACTION = "card_action"
	INSTALL = "install"
	UNINSTALL = "uninstall"
	IGNORED = "ignored"


# Reason codes (TeamsAuthResult.reason, Gateway Event rejection reasons).
REASON_OK = "ok"
REASON_MISSING_HEADER = "missing_authorization"
REASON_MALFORMED_TOKEN = "malformed_token"
REASON_BAD_ALGORITHM = "bad_algorithm"
REASON_UNKNOWN_KEY = "unknown_key_id"
REASON_BAD_SIGNATURE = "bad_signature"
REASON_EXPIRED = "token_expired"
REASON_NOT_YET_VALID = "token_not_yet_valid"
REASON_BAD_AUDIENCE = "audience_mismatch"
REASON_BAD_ISSUER = "issuer_not_allowed"
REASON_SERVICE_URL_MISMATCH = "service_url_mismatch"
REASON_BAD_ENDORSEMENT = "channel_not_endorsed"
REASON_METADATA_UNAVAILABLE = "metadata_unavailable"
REASON_TENANT_NOT_ALLOWED = "tenant_not_allowed"
REASON_NOT_LINKED = "identity_not_linked"

AUTH_REASONS = frozenset(
	{
		REASON_OK,
		REASON_MISSING_HEADER,
		REASON_MALFORMED_TOKEN,
		REASON_BAD_ALGORITHM,
		REASON_UNKNOWN_KEY,
		REASON_BAD_SIGNATURE,
		REASON_EXPIRED,
		REASON_NOT_YET_VALID,
		REASON_BAD_AUDIENCE,
		REASON_BAD_ISSUER,
		REASON_SERVICE_URL_MISMATCH,
		REASON_BAD_ENDORSEMENT,
		REASON_METADATA_UNAVAILABLE,
	}
)

# pre_ingest_filter handlers for provider="microsoft_teams": ascending priority.
# Tenant check MUST run before card actions and commands.
HOOK_PRIORITY_INSTALL = 10  # T4 teams_refs
HOOK_PRIORITY_TENANT = 20  # T5 teams_tenant
HOOK_PRIORITY_CARD_ACTION = 30  # T10 teams_actions
HOOK_PRIORITY_COMMANDS = 40  # T8 teams_help
HOOK_PRIORITY_ORDER = (
	("install", HOOK_PRIORITY_INSTALL),
	("tenant", HOOK_PRIORITY_TENANT),
	("card_action", HOOK_PRIORITY_CARD_ACTION),
	("commands", HOOK_PRIORITY_COMMANDS),
)


@dataclass(frozen=True)
class TeamsMeta:
	"""Teams routing metadata extracted from an activity (see ``teams_meta(event)``)."""

	tenant_id: str = ""
	service_url: str = ""
	conversation_type: str = ""  # personal | groupChat | channel
	conversation_id: str = ""  # full id as sent by Teams (may carry ;messageid=)
	root_id: str = ""  # channel thread root message id ("" outside channels)
	user_aad_id: str = ""
	bot_id: str = ""
	team_id: str = ""
	channel_id: str = ""


@dataclass(frozen=True)
class TeamsAuthResult:
	"""Outcome of inbound bearer verification. ``claims`` is empty unless ``ok``."""

	ok: bool
	reason: str = REASON_OK
	claims: dict = field(default_factory=dict)


JsonFetcher = Callable[[str], Mapping[str, Any]]
Clock = Callable[[], float]


class VerifyBearer(Protocol):
	def __call__(
		self,
		auth_header: str,
		*,
		app_id: str,
		activity_service_url: str,
		fetch_json: JsonFetcher,
		now: Clock,
	) -> TeamsAuthResult:
		"""teams_auth.verify_bearer: RS256 only, OpenID->JWKS (kid-miss refresh), iss table,
		aud == app_id, exp/nbf with CLOCK_SKEW_SECONDS, serviceUrl claim == activity serviceUrl,
		``endorsements`` containing ``msteams`` when present. Never raises; failures return
		``TeamsAuthResult(False, <reason code>, {})``."""


class GetBotToken(Protocol):
	def __call__(
		self,
		*,
		app_id: str,
		app_password: str,
		tenant_id: str,
		token_fetcher: Callable[..., Mapping[str, Any]] | None = None,
		now: Clock | None = None,
	) -> str:
		"""teams_auth/teams_api.get_bot_token: client-credentials access token for
		BOT_TOKEN_SCOPE, cached until shortly before expiry. Never log the token."""


class EnqueueOutbound(Protocol):
	def __call__(
		self,
		*,
		gateway: str,
		kind: str,  # reply | card | card_update | proactive
		payload: Mapping[str, Any],
		idempotency_key: str,
		conversation_ref: str | None = None,
	) -> str:
		"""teams_outbox.enqueue: create a Teams Outbound Message row (idempotent on
		``idempotency_key``) and schedule delivery. Returns the row name."""


class UpsertReference(Protocol):
	def __call__(self, gateway: str, meta: TeamsMeta, *, installed: bool = True) -> str:
		"""teams_refs.upsert_reference: create/update the Teams Conversation Reference
		for this conversation; returns its name."""


class ResolveUser(Protocol):
	def __call__(self, gateway: str, tenant_id: str, user_aad_id: str) -> str | None:
		"""teams_identity.resolve_user: Huf user linked to (tenant, aadObjectId) via an
		active Gateway Identity Link, else None. Never falls back to execution_user."""


PROTOCOLS = {
	"teams_auth.verify_bearer": VerifyBearer,
	"teams_auth.get_bot_token": GetBotToken,
	"teams_outbox.enqueue": EnqueueOutbound,
	"teams_refs.upsert_reference": UpsertReference,
	"teams_identity.resolve_user": ResolveUser,
}


def verify_bearer(
	auth_header: str,
	*,
	app_id: str,
	activity_service_url: str,
	fetch_json: JsonFetcher,
	now: Clock,
) -> TeamsAuthResult:
	"""Stub; implemented by T1 in ``teams_auth``. See ``VerifyBearer``."""
	raise NotImplementedError("teams_auth.verify_bearer is implemented by T1")


def get_bot_token(
	*,
	app_id: str,
	app_password: str,
	tenant_id: str,
	token_fetcher: Callable[..., Mapping[str, Any]] | None = None,
	now: Clock | None = None,
) -> str:
	"""Stub; implemented by T2. See ``GetBotToken``."""
	raise NotImplementedError("get_bot_token is implemented by T2")


def enqueue(
	*,
	gateway: str,
	kind: str,
	payload: Mapping[str, Any],
	idempotency_key: str,
	conversation_ref: str | None = None,
) -> str:
	"""Stub; implemented by T6 in ``teams_outbox``. See ``EnqueueOutbound``."""
	raise NotImplementedError("teams_outbox.enqueue is implemented by T6")


def upsert_reference(gateway: str, meta: TeamsMeta, *, installed: bool = True) -> str:
	"""Stub; implemented by T4 in ``teams_refs``. See ``UpsertReference``."""
	raise NotImplementedError("teams_refs.upsert_reference is implemented by T4")


def resolve_user(gateway: str, tenant_id: str, user_aad_id: str) -> str | None:
	"""Stub; implemented by T7 in ``teams_identity``. See ``ResolveUser``."""
	raise NotImplementedError("teams_identity.resolve_user is implemented by T7")
