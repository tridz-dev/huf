"""Offline fixtures for the Microsoft Teams (Bot Framework) gateway tests.

Pure Python: stdlib + PyJWT + cryptography. Importing this module needs no
Frappe site and makes no network calls. Everything network-shaped (the
Bot Framework OpenID/JWKS endpoints, the AAD token endpoint and the Bot
Connector service) is served by ``fake_bot_services()`` on 127.0.0.1.

Public API (see the section headers below for details):

Activity builders (return plain dicts):
    personal_message, group_chat_message, channel_mention_message,
    channel_message, reply_message, conversation_update, typing_activity,
    message_reaction, invoke_activity, installation_update,
    message_with_file_download, message_with_inline_html,
    message_from_other_tenant

Key / JWT toolkit:
    SigningKey, generate_keypair, build_jwks, build_openid_config,
    make_bot_token, forged_token, wrong_audience_token, wrong_issuer_token,
    expired_token, service_url_mismatch_token, unknown_kid_token,
    TOKEN_VARIANTS

Fake services:
    FakeBotServices, fake_bot_services
"""

from __future__ import annotations

import copy
import http.server
import itertools
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOT_APP_ID = "8f1d2c3b-4a5e-4f6a-9b7c-1d2e3f4a5b6c"
BOT_ID = f"28:{BOT_APP_ID}"
BOT_NAME = "Huf Bot"
TENANT_ID = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT_ID = "99999999-8888-7777-6666-555555555555"
DEFAULT_SERVICE_URL = "https://smba.trafficmanager.net/amer/"
DEFAULT_KID = "fixture-key-1"
BOT_FRAMEWORK_ISSUER = "https://api.botframework.com"
BOT_FRAMEWORK_JWKS_URI = "https://login.botframework.com/v1/.well-known/keys"
CHANNEL_ID = "msteams"
# Claim name used for the serviceUrl claim in the inbound JWT. The spec in
# the Teams recon says "serviceUrl"; real SDK tokens are believed to use the
# lowercase "serviceurl" (UNVERIFIED against a live tenant).
SERVICE_URL_CLAIM = "serviceUrl"
CLOCK_SKEW_SECONDS = 300

_ACTIVITY_IDS = itertools.count(1712345678901)


def _next_activity_id() -> str:
    return str(next(_ACTIVITY_IDS))


# ---------------------------------------------------------------------------
# Activity builders
# ---------------------------------------------------------------------------


def _tenant_channel_data(tenant_id: str) -> dict[str, Any]:
    return {"tenant": {"id": tenant_id}}


def _base_activity(
    *,
    activity_type: str,
    conversation_id: str,
    conversation_type: str,
    text: str | None,
    service_url: str,
    from_id: str,
    from_name: str,
    from_aad: str,
    tenant_id: str,
    activity_id: str | None = None,
    reply_to_id: str | None = None,
    channel_data: dict[str, Any] | None = None,
    is_group: bool | None = None,
) -> dict[str, Any]:
    conversation: dict[str, Any] = {
        "id": conversation_id,
        "conversationType": conversation_type,
        "tenantId": tenant_id,
    }
    if is_group is not None:
        conversation["isGroup"] = is_group
    activity: dict[str, Any] = {
        "type": activity_type,
        "id": activity_id or _next_activity_id(),
        "channelId": CHANNEL_ID,
        "serviceUrl": service_url,
        "from": {"id": from_id, "name": from_name, "aadObjectId": from_aad},
        "recipient": {"id": BOT_ID, "name": BOT_NAME},
        "conversation": conversation,
        "channelData": channel_data if channel_data is not None else _tenant_channel_data(tenant_id),
        "locale": "en-US",
        "localTimestamp": "2026-10-27T09:00:00.000+00:00",
        "timestamp": "2026-10-27T09:00:00.000Z",
    }
    if text is not None:
        activity["text"] = text
    if reply_to_id is not None:
        activity["replyToId"] = reply_to_id
    return activity


def personal_message(
    text: str = "hello from a 1:1 chat",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
    from_name: str = "Ada Lovelace",
    from_aad: str = "aaaaaaaa-0000-4000-8000-000000000001",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """1:1 ('personal') message. Conversation id uses the ``a:`` prefix Teams uses."""
    return _base_activity(
        activity_type="message",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=text,
        service_url=service_url,
        from_id=f"29:1{from_aad}-fixture",
        from_name=from_name,
        from_aad=from_aad,
        tenant_id=tenant_id,
        activity_id=activity_id,
    )


def group_chat_message(
    text: str = "group chat hello",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "19:groupchatfixture0001@thread.v2",
    from_name: str = "Grace Hopper",
    from_aad: str = "aaaaaaaa-0000-4000-8000-000000000002",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Group chat message (no @mention required by Teams for group chats)."""
    return _base_activity(
        activity_type="message",
        conversation_id=conversation_id,
        conversation_type="groupChat",
        text=text,
        service_url=service_url,
        from_id=f"29:1{from_aad}-fixture",
        from_name=from_name,
        from_aad=from_aad,
        tenant_id=tenant_id,
        activity_id=activity_id,
        is_group=True,
    )


CHANNEL_CONVERSATION_BASE = "19:channelfixture0001@thread.tacv2"
CHANNEL_ROOT_MESSAGE_ID = "1712345670000"


def _channel_channel_data(tenant_id: str) -> dict[str, Any]:
    return {
        "tenant": {"id": tenant_id},
        "team": {
            "id": "19:teamfixture0001@thread.tacv2",
            "name": "Huf Fixtures",
            "aadGroupId": "bbbbbbbb-0000-4000-8000-000000000010",
        },
        "channel": {"id": CHANNEL_CONVERSATION_BASE, "name": "general"},
        "eventType": "",
    }


def _channel_conversation_id(thread_root_id: str | None) -> str:
    if thread_root_id is None:
        return CHANNEL_CONVERSATION_BASE
    return f"{CHANNEL_CONVERSATION_BASE};messageid={thread_root_id}"


def channel_mention_message(
    text: str = f"<at>{BOT_NAME}</at> what is on the roadmap?",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    thread_root_id: str | None = CHANNEL_ROOT_MESSAGE_ID,
    from_name: str = "Linus Torvalds",
    from_aad: str = "aaaaaaaa-0000-4000-8000-000000000003",
    activity_id: str | None = None,
    mention_text: str = BOT_NAME,
) -> dict[str, Any]:
    """Channel message that @mentions the bot.

    The ``entities[]`` mention (``mentioned.id == BOT_ID``) is the authoritative
    signal; the ``<at>..</at>`` markup in ``text`` mirrors it. A channel thread
    id carries ``;messageid=<root>`` when ``thread_root_id`` is given.
    """
    activity = _base_activity(
        activity_type="message",
        conversation_id=_channel_conversation_id(thread_root_id),
        conversation_type="channel",
        text=text,
        service_url=service_url,
        from_id=f"29:1{from_aad}-fixture",
        from_name=from_name,
        from_aad=from_aad,
        tenant_id=tenant_id,
        activity_id=activity_id,
        channel_data=_channel_channel_data(tenant_id),
        is_group=True,
    )
    activity["entities"] = [
        {
            "type": "mention",
            "text": f"<at>{mention_text}</at>",
            "mentioned": {"id": BOT_ID, "name": BOT_NAME},
        }
    ]
    return activity


def channel_message(
    text: str = "plain channel chatter, no mention",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    thread_root_id: str | None = None,
    from_name: str = "Linus Torvalds",
    from_aad: str = "aaaaaaaa-0000-4000-8000-000000000003",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Channel message without a bot mention (should be ignored by the bot)."""
    activity = _base_activity(
        activity_type="message",
        conversation_id=_channel_conversation_id(thread_root_id),
        conversation_type="channel",
        text=text,
        service_url=service_url,
        from_id=f"29:1{from_aad}-fixture",
        from_name=from_name,
        from_aad=from_aad,
        tenant_id=tenant_id,
        activity_id=activity_id,
        channel_data=_channel_channel_data(tenant_id),
        is_group=True,
    )
    activity["entities"] = []
    return activity


def reply_message(
    reply_to_id: str,
    text: str = "replying to your earlier message",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
    from_name: str = "Ada Lovelace",
    from_aad: str = "aaaaaaaa-0000-4000-8000-000000000001",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Message with ``replyToId`` set to the activity it answers (personal chat by default)."""
    return _base_activity(
        activity_type="message",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=text,
        service_url=service_url,
        from_id=f"29:1{from_aad}-fixture",
        from_name=from_name,
        from_aad=from_aad,
        tenant_id=tenant_id,
        activity_id=activity_id,
        reply_to_id=reply_to_id,
    )


def conversation_update(
    members_added: Iterable[Mapping[str, str]] | None = None,
    *,
    members_removed: Iterable[Mapping[str, str]] | None = None,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
    conversation_type: str = "personal",
) -> dict[str, Any]:
    """conversationUpdate with membersAdded (bot install / user joined) and optional membersRemoved."""
    if members_added is None:
        members_added = [{"id": BOT_ID, "name": BOT_NAME}]
    activity = _base_activity(
        activity_type="conversationUpdate",
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        text=None,
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
    )
    activity["membersAdded"] = [dict(m) for m in members_added]
    activity["membersRemoved"] = [dict(m) for m in (members_removed or [])]
    return activity


def installation_update(
    action: str = "add",
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
) -> dict[str, Any]:
    """conversationUpdate carrying ``action`` (add/remove) for app install/uninstall."""
    activity = conversation_update(
        service_url=service_url,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
    )
    activity.pop("membersAdded", None)
    activity.pop("membersRemoved", None)
    activity["action"] = action
    activity["channelData"] = {"tenant": {"id": tenant_id}, "eventType": "teamMemberAdded" if action == "add" else "teamMemberRemoved"}
    return activity


def typing_activity(
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
) -> dict[str, Any]:
    """typing activity (no text, no entities)."""
    return _base_activity(
        activity_type="typing",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=None,
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
    )


def message_reaction(
    reactions_added: Iterable[str] = ("like",),
    *,
    reply_to_id: str = "1712345670000",
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
) -> dict[str, Any]:
    """messageReaction with reactionsAdded (types such as 'like', 'heart')."""
    activity = _base_activity(
        activity_type="messageReaction",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=None,
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
        reply_to_id=reply_to_id,
    )
    activity["reactionsAdded"] = [{"type": r} for r in reactions_added]
    activity["reactionsRemoved"] = []
    return activity


def invoke_activity(
    name: str = "fileConsent/invoke",
    value: Mapping[str, Any] | None = None,
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
) -> dict[str, Any]:
    """invoke activity, e.g. ``fileConsent/invoke`` or ``adaptiveCard/action``."""
    activity = _base_activity(
        activity_type="invoke",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=None,
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
    )
    activity["name"] = name
    activity["value"] = dict(value) if value is not None else {"action": "accept"}
    return activity


def message_with_file_download(
    text: str = "here is the report",
    *,
    download_url: str = "https://contoso-my.sharepoint.com/personal/ada_fixture/_layouts/download.aspx?fixture=1",
    file_name: str = "report.pdf",
    file_type: str = "pdf",
    unique_id: str = "7c1e0b9a-0000-4000-8000-00000000f11e",
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Personal-chat message carrying a ``file.download.info`` attachment (pre-authed download URL)."""
    activity = _base_activity(
        activity_type="message",
        conversation_id=conversation_id,
        conversation_type="personal",
        text=text,
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
        activity_id=activity_id,
    )
    activity["attachments"] = [
        {
            "contentType": "application/vnd.microsoft.teams.file.download.info",
            "contentUrl": download_url,
            "name": file_name,
            "content": {
                "downloadUrl": download_url,
                "uniqueId": unique_id,
                "fileType": file_type,
            },
        }
    ]
    return activity


def message_with_inline_html(
    html: str = '<p>Inline <b>HTML</b> card</p>',
    *,
    service_url: str = DEFAULT_SERVICE_URL,
    tenant_id: str = TENANT_ID,
    conversation_id: str = "a:1QxCcZ3gA-personal-fixture",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Message with an inline ``text/html`` attachment (content carries the markup)."""
    activity = _base_activity(
        activity_type="message",
        conversation_id=conversation_id,
        conversation_type="personal",
        text="",
        service_url=service_url,
        from_id="29:1aaaaaaaa-0000-4000-8000-000000000001-fixture",
        from_name="Ada Lovelace",
        from_aad="aaaaaaaa-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
        activity_id=activity_id,
    )
    activity["attachments"] = [
        {"contentType": "text/html", "content": html, "name": None, "contentUrl": None}
    ]
    return activity


def message_from_other_tenant(
    text: str = f"<at>{BOT_NAME}</at> hi from elsewhere",
    *,
    foreign_tenant_id: str = OTHER_TENANT_ID,
    service_url: str = DEFAULT_SERVICE_URL,
) -> dict[str, Any]:
    """Channel @mention whose ``channelData.tenant.id`` is a tenant other than the bot's home tenant."""
    activity = channel_mention_message(
        text=text,
        service_url=service_url,
        tenant_id=foreign_tenant_id,
        from_name="Mallory Foreign",
        from_aad="cccccccc-0000-4000-8000-000000000009",
    )
    return activity


# ---------------------------------------------------------------------------
# Key / JWT toolkit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SigningKey:
    """An RSA key pair with its key id. ``private_pem`` signs, ``public_jwk`` goes in the JWKS."""

    kid: str
    private_key: rsa.RSAPrivateKey = field(repr=False)

    @property
    def private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    @property
    def public_jwk(self) -> dict[str, Any]:
        jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256", "kty": "RSA"})
        return jwk


def generate_keypair(kid: str = DEFAULT_KID, key_size: int = 2048) -> SigningKey:
    """Generate a fresh RSA key pair. No files are written."""
    return SigningKey(kid=kid, private_key=rsa.generate_private_key(public_exponent=65537, key_size=key_size))


_DEFAULT_KEY: SigningKey | None = None
_DEFAULT_KEY_LOCK = threading.Lock()


def default_signing_key() -> SigningKey:
    """Process-wide key used when a helper is not given an explicit ``key``."""
    global _DEFAULT_KEY
    with _DEFAULT_KEY_LOCK:
        if _DEFAULT_KEY is None:
            _DEFAULT_KEY = generate_keypair(DEFAULT_KID)
        return _DEFAULT_KEY


def build_jwks(*keys: SigningKey, endorsements: Iterable[str] = (CHANNEL_ID,)) -> dict[str, Any]:
    """Build a JWKS document. Each key carries Bot Framework-style ``endorsements``."""
    endorsed = list(endorsements)
    doc_keys = []
    for key in keys:
        jwk = key.public_jwk
        jwk["endorsements"] = endorsed
        doc_keys.append(jwk)
    return {"keys": doc_keys}


def build_openid_config(
    jwks_uri: str = BOT_FRAMEWORK_JWKS_URI,
    issuer: str = BOT_FRAMEWORK_ISSUER,
) -> dict[str, Any]:
    """OpenID metadata mirroring the shape of login.botframework.com's openidconfiguration."""
    return {
        "issuer": issuer,
        "authorization_endpoint": "https://webchat.botframework.com/api/oauth/authorize",
        "jwks_uri": jwks_uri,
        "id_token_signing_alg_values_supported": ["RS256"],
        "subject_types_supported": ["pairwise"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "response_types_supported": ["id_token"],
        "response_modes_supported": ["form_post"],
        "claims_supported": ["aud", "exp", "iat", "iss", "nbf", "serviceUrl"],
    }


def make_bot_token(
    activity: Mapping[str, Any] | None = None,
    *,
    app_id: str = BOT_APP_ID,
    kid: str = DEFAULT_KID,
    issuer: str = BOT_FRAMEWORK_ISSUER,
    audience: str | None = None,
    service_url: str | None = None,
    exp_delta: int = 3600,
    nbf_delta: int = 0,
    extra_claims: Mapping[str, Any] | None = None,
    key: SigningKey | None = None,
) -> str:
    """Create an RS256 Bot Framework-style inbound JWT.

    ``audience`` defaults to ``app_id``; ``service_url`` defaults to the
    activity's ``serviceUrl`` (or DEFAULT_SERVICE_URL without an activity).
    ``exp_delta``/``nbf_delta`` are relative to now (negative exp_delta gives an
    expired token). The signing key defaults to the process-wide key, whose
    public half is what ``build_jwks(default_signing_key())`` publishes.
    """
    signing_key = key or default_signing_key()
    now = int(time.time())
    if service_url is None:
        service_url = activity.get("serviceUrl", DEFAULT_SERVICE_URL) if activity else DEFAULT_SERVICE_URL
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience if audience is not None else app_id,
        "iat": now,
        "nbf": now + nbf_delta,
        "exp": now + exp_delta,
        SERVICE_URL_CLAIM: service_url,
        "appid": app_id,
    }
    if extra_claims:
        claims.update(extra_claims)
    return pyjwt.encode(claims, signing_key.private_pem, algorithm="RS256", headers={"kid": kid})


def forged_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID, kid: str = DEFAULT_KID) -> str:
    """Token claiming ``kid`` but signed by a different, attacker-held key."""
    attacker = generate_keypair(kid=kid, key_size=2048)
    return make_bot_token(activity, app_id=app_id, kid=kid, key=attacker)


def wrong_audience_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID, kid: str = DEFAULT_KID) -> str:
    """Correctly signed token whose ``aud`` is another app id."""
    return make_bot_token(activity, app_id=app_id, kid=kid, audience="00000000-0000-4000-8000-0000000000ff")


def wrong_issuer_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID, kid: str = DEFAULT_KID) -> str:
    """Correctly signed token whose ``iss`` is not api.botframework.com."""
    return make_bot_token(activity, app_id=app_id, kid=kid, issuer="https://sts.windows.net/evil-tenant/")


def expired_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID, kid: str = DEFAULT_KID) -> str:
    """Correctly signed token that expired well beyond the 5 minute clock skew."""
    return make_bot_token(activity, app_id=app_id, kid=kid, exp_delta=-(CLOCK_SKEW_SECONDS * 4))


def service_url_mismatch_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID, kid: str = DEFAULT_KID) -> str:
    """Correctly signed token whose serviceUrl claim differs from the activity's serviceUrl."""
    return make_bot_token(activity, app_id=app_id, kid=kid, service_url="https://attacker.example.com/")


def unknown_kid_token(activity: Mapping[str, Any] | None = None, *, app_id: str = BOT_APP_ID) -> str:
    """Token signed by the real key but advertising a kid absent from the JWKS."""
    return make_bot_token(activity, app_id=app_id, kid="kid-not-in-jwks")


TOKEN_VARIANTS: dict[str, Callable[..., str]] = {
    "forged_signature": forged_token,
    "wrong_audience": wrong_audience_token,
    "wrong_issuer": wrong_issuer_token,
    "expired": expired_token,
    "service_url_mismatch": service_url_mismatch_token,
    "unknown_kid": unknown_kid_token,
}


# ---------------------------------------------------------------------------
# Fake services (OpenID/JWKS, AAD token endpoint, Bot Connector)
# ---------------------------------------------------------------------------

TOKEN_PATH_SUFFIX = "/oauth2/v2.0/token"
OPENID_PATH = "/v1/.well-known/openidconfiguration"
JWKS_PATH = "/v1/.well-known/keys"
CONNECTOR_PREFIX = "/v3/conversations/"

_SENSITIVE_FORM_FIELDS = frozenset({"client_secret", "password", "assertion"})


@dataclass
class Step:
    """One scripted response: HTTP status, extra headers, optional JSON/raw body."""

    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None


def _as_step(item: Any) -> Step:
    if isinstance(item, Step):
        return item
    if isinstance(item, int):
        return Step(status=item)
    if isinstance(item, tuple):
        status, headers = item
        return Step(status=status, headers=dict(headers))
    if isinstance(item, Mapping):
        return Step(status=item.get("status", 200), headers=dict(item.get("headers", {})), body=item.get("body"))
    raise TypeError(f"unsupported scripted step: {item!r}")


@dataclass(frozen=True)
class RequestRecord:
    endpoint: str
    method: str
    path: str
    headers: dict[str, str]
    has_authorization: bool
    body: Any  # parsed JSON for connector; redacted form dict for token endpoint; None for GET


class FakeBotServices:
    """Handle returned by ``fake_bot_services()``. Thread-safe request log and scripts."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.openid_url = base_url + OPENID_PATH
        self.jwks_url = base_url + JWKS_PATH
        self.token_url_for = lambda tenant: f"{base_url}/{tenant}{TOKEN_PATH_SUFFIX}"
        self.connector_url = base_url + "/"  # use as serviceUrl in activities
        self._lock = threading.Lock()
        self._log: list[RequestRecord] = []
        self._scripts: dict[str, list[Step]] = {"openid": [], "jwks": [], "token": [], "connector": []}
        self._counter = itertools.count(1)
        self.jwks: dict[str, Any] = {"keys": []}
        self.openid: dict[str, Any] = build_openid_config(jwks_uri=self.jwks_url)
        self.access_token_prefix = "fake-access-token"
        self.token_expires_in = 3600

    # -- configuration -----------------------------------------------------

    def set_jwks(self, jwks: Mapping[str, Any]) -> None:
        with self._lock:
            self.jwks = copy.deepcopy(dict(jwks))

    def set_openid(self, openid: Mapping[str, Any]) -> None:
        with self._lock:
            self.openid = copy.deepcopy(dict(openid))

    def script(self, endpoint: str, *steps: Any) -> None:
        """Queue scripted responses for ``endpoint`` ('openid'|'jwks'|'token'|'connector').

        Each step is an int status, ``(status, headers_dict)``, a ``Step`` or a
        mapping ``{"status", "headers", "body"}``. Consumed FIFO; once the queue
        is empty the endpoint answers normally (200).
        """
        if endpoint not in self._scripts:
            raise KeyError(endpoint)
        with self._lock:
            self._scripts[endpoint].extend(_as_step(s) for s in steps)

    # -- inspection --------------------------------------------------------

    def requests(self, endpoint: str | None = None) -> list[RequestRecord]:
        with self._lock:
            return [r for r in self._log if endpoint is None or r.endpoint == endpoint]

    def clear_log(self) -> None:
        with self._lock:
            self._log.clear()

    # -- internals used by the handler -------------------------------------

    def _next_step(self, endpoint: str) -> Step | None:
        with self._lock:
            queue = self._scripts[endpoint]
            return queue.pop(0) if queue else None

    def _record(self, record: RequestRecord) -> None:
        with self._lock:
            self._log.append(record)

    def _next_number(self) -> int:
        with self._lock:
            return next(self._counter)


def _make_handler(services: FakeBotServices) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # silence stderr access logs
            return

        # -- helpers ---------------------------------------------------------

        def _headers_snapshot(self) -> tuple[dict[str, str], bool]:
            has_auth = self.headers.get("Authorization") is not None
            snap = {k: v for k, v in self.headers.items() if k.lower() != "authorization"}
            if has_auth:
                snap["Authorization"] = "<present>"
            return snap, has_auth

        def _send(self, status: int, payload: Any, headers: Mapping[str, str] | None = None) -> None:
            raw = b"" if payload is None else (payload if isinstance(payload, bytes) else json.dumps(payload).encode())
            self.send_response(status)
            if raw:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _scripted_or(self, endpoint: str, default: Callable[[], tuple[int, Any, dict[str, str]]]) -> None:
            step = services._next_step(endpoint)
            if step is None:
                status, payload, headers = default()
            else:
                status = step.status
                headers = step.headers
                payload = step.body if step.body is not None else {"error": "scripted", "status": status}
                if 200 <= status < 300 and step.body is None:
                    _, payload, _ = default()
            self._send(status, payload, headers)

        # -- routes ----------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.urlsplit(self.path).path
            headers, has_auth = self._headers_snapshot()
            if path == OPENID_PATH:
                services._record(RequestRecord("openid", "GET", path, headers, has_auth, None))
                self._scripted_or("openid", lambda: (200, services.openid, {}))
            elif path == JWKS_PATH:
                services._record(RequestRecord("jwks", "GET", path, headers, has_auth, None))
                self._scripted_or("jwks", lambda: (200, services.jwks, {}))
            else:
                services._record(RequestRecord("other", "GET", path, headers, has_auth, None))
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            self._handle_write("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._handle_write("PUT")

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle_write("DELETE")

        def _handle_write(self, method: str) -> None:
            path = urllib.parse.urlsplit(self.path).path
            raw = self._read_body()
            headers, has_auth = self._headers_snapshot()
            if path.endswith(TOKEN_PATH_SUFFIX):
                form = {k: v[-1] for k, v in urllib.parse.parse_qs(raw.decode(), keep_blank_values=True).items()}
                redacted = {k: v for k, v in form.items() if k not in _SENSITIVE_FORM_FIELDS}
                redacted["client_secret_sent"] = "client_secret" in form
                services._record(RequestRecord("token", method, path, headers, has_auth, redacted))
                self._scripted_or("token", lambda: self._token_default())
                return
            if path.startswith(CONNECTOR_PREFIX):
                body: Any = None
                if raw:
                    try:
                        body = json.loads(raw.decode())
                    except ValueError:
                        body = raw.decode(errors="replace")
                services._record(RequestRecord("connector", method, path, headers, has_auth, body))
                self._scripted_or("connector", lambda: (200, {"id": f"fake-activity-{services._next_number()}"}, {}))
                return
            services._record(RequestRecord("other", method, path, headers, has_auth, None))
            self._send(404, {"error": "not found"})

        def _token_default(self) -> tuple[int, Any, dict[str, str]]:
            return (
                200,
                {
                    "token_type": "Bearer",
                    "expires_in": services.token_expires_in,
                    "access_token": f"{services.access_token_prefix}-{services._next_number()}",
                },
                {},
            )

    return Handler


@contextmanager
def fake_bot_services() -> Iterator[FakeBotServices]:
    """Start the fake OpenID/JWKS, token and connector server on 127.0.0.1 (ephemeral port).

    Yields a ``FakeBotServices``. The server is shut down on exit. Clients must
    bypass proxies (see ``http_request``) so local traffic is never routed away.
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    services = FakeBotServices(base_url)
    server.RequestHandlerClass = _make_handler(services)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield services
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_request(
    method: str,
    url: str,
    *,
    json_body: Any = None,
    form: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, str], Any]:
    """Tiny proxy-free client for the fake services. Returns (status, headers, parsed_json_or_text)."""
    data: bytes | None = None
    req_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        req_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            status, resp_headers, raw = resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        status, resp_headers = exc.code, dict(exc.headers.items())
        raw = exc.read()
        exc.close()
    text = raw.decode(errors="replace")
    try:
        return status, resp_headers, json.loads(text) if text else None
    except ValueError:
        return status, resp_headers, text


def new_request_id() -> str:
    """Convenience: a fresh GUID for activity/correlation ids in tests."""
    return str(uuid.uuid4())
