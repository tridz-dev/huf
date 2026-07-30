# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Hub readiness & provider introspection API (M2).

Endpoints backing the simplified hub homepage:

- get_hub_readiness():          is the Hub Orchestrator usable, and if not,
                                what should the user fix (remediation hints).
- get_provider_status():        per-provider `configured` flags. Never returns
                                or logs API key material.
- get_model_catalog_proposals(): read-only diff of a curated catalog snapshot
                                (CATALOG_CANDIDATES, verified online) against
                                existing AI Model records.
- approve_model_proposals():    manager-gated insert of approved proposals.

Security note: API keys are only ever checked for presence via
``get_password("api_key")``; key values are never read into a returned dict.
"""

import frappe
from frappe import _

from huf.ai.app_seeding.hub_orchestrator import HUB_AGENT_NAME

# Date the CATALOG_CANDIDATES snapshot below was verified against public
# provider docs/announcements. Bump whenever the list is refreshed.
CATALOG_RETRIEVED_AT = "2026-07-25"

# Curated catalog proposals, verified against public sources on
# CATALOG_RETRIEVED_AT (see module docstring / PR notes for citations).
# Each entry: model_name, provider_brand (AI Provider.provider_brand),
# modalities (AI Model.modalities hint values), source, retrieved_at.
CATALOG_CANDIDATES = [
    # OpenAI — GPT-5.2 family is the current flagship line.
    {"model_name": "gpt-5.2", "provider_brand": "openai", "modalities": "Text, Vision",
     "source_url": "https://platform.openai.com/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "gpt-5.2-mini", "provider_brand": "openai", "modalities": "Text, Vision",
     "source_url": "https://platform.openai.com/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "gpt-5.2-nano", "provider_brand": "openai", "modalities": "Text",
     "source_url": "https://platform.openai.com/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # Anthropic — Opus 4.8 flagship; Sonnet 5 is the current default Sonnet.
    {"model_name": "claude-opus-4.8", "provider_brand": "anthropic", "modalities": "Text, Vision",
     "source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "claude-sonnet-5", "provider_brand": "anthropic", "modalities": "Text, Vision",
     "source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # Google — 3.1 Pro preview is the flagship; 3.5 Flash is the GA default;
    # 3 Flash preview is the cheap value pick.
    {"model_name": "gemini-3.1-pro-preview", "provider_brand": "google", "modalities": "Text, Vision",
     "source_url": "https://ai.google.dev/gemini-api/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "gemini-3.5-flash", "provider_brand": "google", "modalities": "Text, Vision",
     "source_url": "https://ai.google.dev/gemini-api/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "gemini-3-flash-preview", "provider_brand": "google", "modalities": "Text, Vision",
     "source_url": "https://ai.google.dev/gemini-api/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # OpenRouter — namespaced IDs, following the seeded convention.
    {"model_name": "openai/gpt-5.2", "provider_brand": "openrouter", "modalities": "Text, Vision",
     "source_url": "https://openrouter.ai/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "google/gemini-3.5-flash", "provider_brand": "openrouter", "modalities": "Text, Vision",
     "source_url": "https://openrouter.ai/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # xAI — grok-4.5 flagship; grok-4.1-fast is the cheap high-context pick.
    {"model_name": "grok-4.5", "provider_brand": "xai", "modalities": "Text",
     "source_url": "https://docs.x.ai/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "grok-4.1-fast", "provider_brand": "xai", "modalities": "Text",
     "source_url": "https://docs.x.ai/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # Groq — fast LPU serving of open-weight Llama.
    {"model_name": "llama-3.3-70b-versatile", "provider_brand": "groq", "modalities": "Text",
     "source_url": "https://console.groq.com/docs/models",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # DeepSeek — official V4 API IDs (deepseek-chat/-reasoner deprecated 2026-07-24).
    {"model_name": "deepseek-v4-pro", "provider_brand": "deepseek", "modalities": "Text",
     "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "deepseek-v4-flash", "provider_brand": "deepseek", "modalities": "Text",
     "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    # Moonshot — K2.6 is the current flagship; K2.5 the cheaper tier.
    # NOTE: "moonshot" is not (yet) an AI Provider.provider_brand option, so
    # these proposals resolve provider=None until a matching provider exists.
    {"model_name": "kimi-k2.6", "provider_brand": "moonshot", "modalities": "Text, Vision",
     "source_url": "https://platform.moonshot.cn/docs/intro",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
    {"model_name": "kimi-k2.5", "provider_brand": "moonshot", "modalities": "Text, Vision",
     "source_url": "https://platform.moonshot.cn/docs/intro",
     "source": "web", "retrieved_at": CATALOG_RETRIEVED_AT},
]

# Roles allowed to approve model catalog proposals.
_MODEL_MANAGER_ROLES = ("System Manager", "Huf Manager")


def _require_agent_read() -> None:
    """Read endpoints require an authenticated user with Agent read access."""
    if not frappe.has_permission("Agent", "read"):
        frappe.throw(
            _("You don't have permission to view hub status."),
            frappe.PermissionError,
        )


def _require_provider_read() -> None:
    """Provider introspection requires AI Provider read access."""
    if not frappe.has_permission("AI Provider", "read"):
        frappe.throw(
            _("You don't have permission to view provider status."),
            frappe.PermissionError,
        )


def _require_model_read() -> None:
    """Catalog proposals require AI Model read access."""
    if not frappe.has_permission("AI Model", "read"):
        frappe.throw(
            _("You don't have permission to view model catalog proposals."),
            frappe.PermissionError,
        )


def _require_model_manager() -> None:
    """Approve endpoint is restricted to System Manager / Huf Manager."""
    if not set(frappe.get_roles()).intersection(_MODEL_MANAGER_ROLES):
        frappe.throw(
            _("Only System Managers or Huf Managers can approve model proposals."),
            frappe.PermissionError,
        )


def _provider_has_key(provider_name) -> bool:
    """True only if the provider exists and has an api_key. Never returns the value."""
    if not provider_name or not frappe.db.exists("AI Provider", provider_name):
        return False
    try:
        return bool(frappe.get_doc("AI Provider", provider_name).get_password("api_key", raise_exception=False))
    except Exception:
        # Frappe raises AuthenticationError ("Password not found") when no password row exists at all.
        return False


def _count_keyed_providers() -> int:
    """Number of AI Providers that have a non-empty api_key."""
    return sum(
        1
        for name in frappe.get_all("AI Provider", pluck="name")
        if _provider_has_key(name)
    )


def _orchestrator_info() -> dict:
    """Snapshot of the seeded Hub Orchestrator agent's provisioning state."""
    if not frappe.db.exists("Agent", HUB_AGENT_NAME):
        return {"present": False, "disabled": False, "provider": None, "model": None}
    row = frappe.db.get_value(
        "Agent", HUB_AGENT_NAME, ["disabled", "provider", "model"], as_dict=True
    )
    return {
        "present": True,
        "disabled": bool(row.disabled),
        "provider": row.provider or None,
        "model": row.model or None,
    }


def _build_remediation(orchestrator: dict, providers_with_keys: int) -> list:
    """User-facing fix hints, ordered by what blocks readiness first."""
    remediation = []

    if not orchestrator["present"]:
        remediation.append({
            "code": "no_orchestrator",
            "message": _(
                "The Hub Orchestrator agent is missing. Re-run app seeding or "
                "create an agent named '{0}'."
            ).format(HUB_AGENT_NAME),
            "action_route": "/agents",
        })
        if providers_with_keys == 0:
            remediation.append(_no_provider_key_entry())
        return remediation

    if orchestrator["disabled"]:
        remediation.append({
            "code": "orchestrator_disabled",
            "message": _(
                "The Hub Orchestrator agent is disabled. Enable it once a "
                "provider API key is configured."
            ),
            "action_route": "/agents",
        })

    if not orchestrator["provider"] or not _provider_has_key(orchestrator["provider"]):
        if providers_with_keys == 0:
            remediation.append(_no_provider_key_entry())
        else:
            remediation.append({
                "code": "orchestrator_provider_unkeyed",
                "message": _(
                    "The Hub Orchestrator's provider has no API key. Point it "
                    "at a configured provider or add a key to it."
                ),
                "action_route": "/models",
            })

    if not orchestrator["model"]:
        remediation.append({
            "code": "no_model",
            "message": _(
                "The Hub Orchestrator has no model selected. Pick a chat model "
                "for its provider."
            ),
            "action_route": "/models",
        })

    return remediation


def _no_provider_key_entry() -> dict:
    return {
        "code": "no_provider_key",
        "message": _(
            "No AI Provider has an API key yet. Add a key to at least one "
            "provider to enable the hub."
        ),
        "action_route": "/models",
    }


def _provider_for_brand(provider_brand):
    """First AI Provider (by creation) matching a brand, else None."""
    return frappe.db.get_value(
        "AI Provider", {"provider_brand": provider_brand}, "name", order_by="creation asc"
    )


def _set_catalog_metadata(doc, candidate: dict):
    """Persist catalog source/audit fields if the AI Model DocType supports them.

    Keeps the approval auditable without requiring a schema migration: if the
    hidden fields exist they are populated, otherwise the doc proceeds with the
    core fields only.
    """
    for field, value in (
        ("catalog_source", candidate.get("source")),
        ("catalog_source_url", candidate.get("source_url")),
        ("catalog_retrieved_at", candidate.get("retrieved_at")),
        ("catalog_approved_by", frappe.session.user),
        ("catalog_approved_at", frappe.utils.now()),
    ):
        if field in doc.meta.fields:
            doc.set(field, value)


@frappe.whitelist()
def get_hub_readiness():
    """Hub readiness summary for the simplified hub homepage.

    Returns:
        dict: ``orchestrator`` (present/disabled/provider/model/
        provider_configured), ``providers_with_keys``, ``models_available``,
        ``ready``, and ``remediation`` (list of {code, message, action_route}).

    Requires: authenticated user with Agent read access. Read-only.
    """
    _require_agent_read()

    orchestrator = _orchestrator_info()
    providers_with_keys = _count_keyed_providers()
    models_available = frappe.db.count("AI Model")
    provider_configured = _provider_has_key(orchestrator["provider"])

    ready = (
        orchestrator["present"]
        and not orchestrator["disabled"]
        and provider_configured
        and bool(orchestrator["model"])
    )

    return {
        "orchestrator": {
            **orchestrator,
            "provider_configured": provider_configured,
        },
        "providers_with_keys": providers_with_keys,
        "models_available": models_available,
        "ready": ready,
        "remediation": _build_remediation(orchestrator, providers_with_keys),
    }


@frappe.whitelist()
def get_provider_status():
    """Per-provider configuration status. Configured providers sort first.

    `configured` means the provider has a non-empty api_key, or is a local
    LLM provider (is_local_llm) with a url set. The API key value is never
    included.

    Returns:
        list[dict]: name, provider_name, provider_brand, configured,
        is_local_llm, model_count.

    Requires: authenticated user with Agent read access. Read-only.
    """
    _require_agent_read()

    model_counts = {}
    for provider in frappe.get_all("AI Model", pluck="provider"):
        model_counts[provider] = model_counts.get(provider, 0) + 1

    rows = []
    for p in frappe.get_all(
        "AI Provider",
        fields=["name", "provider_name", "provider_brand", "is_local_llm", "url"],
        order_by="provider_name asc",
    ):
        configured = _provider_has_key(p.name) or bool(p.is_local_llm and p.url)
        rows.append({
            "name": p.name,
            "provider_name": p.provider_name,
            "provider_brand": p.provider_brand,
            "configured": configured,
            "is_local_llm": bool(p.is_local_llm),
            "model_count": model_counts.get(p.name, 0),
        })

    rows.sort(key=lambda r: (not r["configured"], (r["provider_name"] or "").lower()))
    return rows


@frappe.whitelist()
def get_model_catalog_proposals():
    """Diff the curated CATALOG_CANDIDATES snapshot against AI Model records.

    READ-ONLY: this endpoint only proposes; it never creates AI Model rows.

    Returns:
        dict: ``proposals`` — list of {model_name, provider (existing AI
        Provider matching the brand, or None), modalities, already_exists}.

    Requires: authenticated user with Agent read access.
    """
    _require_agent_read()

    existing = set(frappe.get_all("AI Model", pluck="model_name"))

    proposals = []
    for candidate in CATALOG_CANDIDATES:
        proposals.append({
            "model_name": candidate["model_name"],
            "provider": _provider_for_brand(candidate["provider_brand"]),
            "modalities": candidate["modalities"],
            "source": candidate.get("source"),
            "source_url": candidate.get("source_url"),
            "retrieved_at": candidate.get("retrieved_at"),
            "already_exists": candidate["model_name"] in existing,
        })
    return {"proposals": proposals}


@frappe.whitelist()
def approve_model_proposals(model_names):
    """Create AI Model rows for approved catalog proposals.

    Only names present in CATALOG_CANDIDATES are considered; proposals whose
    brand has no matching AI Provider, or whose model already exists, are
    skipped. Idempotent.

    Args:
        model_names: list of model names from get_model_catalog_proposals()
            (JSON string accepted for form-encoded calls).

    Returns:
        dict: {"created": [...], "skipped": [...]}

    Requires: System Manager or Huf Manager role.
    """
    _require_model_manager()
    if not frappe.has_permission("AI Model", "create"):
        frappe.throw(
            _("You don't have permission to create AI Model records."),
            frappe.PermissionError,
        )

    if isinstance(model_names, str):
        model_names = frappe.parse_json(model_names)
    if not isinstance(model_names, (list, tuple)):
        frappe.throw(_("model_names must be a list of model names."))

    candidates = {c["model_name"]: c for c in CATALOG_CANDIDATES}

    created, skipped = [], []
    for name in model_names:
        candidate = candidates.get(name)
        if not candidate or frappe.db.exists("AI Model", name):
            skipped.append(name)
            continue

        provider = _provider_for_brand(candidate["provider_brand"])
        if not provider:
            skipped.append(name)
            continue

        doc = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": name,
            "provider": provider,
            "modalities": candidate["modalities"],
        })
        _set_catalog_metadata(doc, candidate)
        doc.insert()
        created.append(name)

    return {"created": created, "skipped": skipped}
