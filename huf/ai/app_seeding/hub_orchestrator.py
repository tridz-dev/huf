"""
Provisioning for the seeded "Hub Orchestrator" system agent.

The versioned seed lives at huf/huf/agents/hub-orchestrator.json (modeled on
demo-assistant.json). Provider/model are deliberately NOT in the seed file:
they are resolved at provision time from the first AI Provider that actually
has an api_key set, so the generic seed upsert can never overwrite a keyed
provider choice.

Entry points:
- create_hub_orchestrator_agent(): called from huf.install after_install and
  after_migrate. Idempotent.
- on_ai_provider_update(doc, method): doc_events hook for "AI Provider"
  on_update; re-provisions the orchestrator when a provider key is first saved.
"""

import json
from contextlib import contextmanager
from pathlib import Path

import frappe

logger = frappe.logger("huf")

HUB_AGENT_NAME = "Hub Orchestrator"
SEED_FILE = "hub-orchestrator.json"

# Ordered chat-model preferences; the first one present in AI Model for the
# chosen provider wins. Falls back to the provider's first non-specialized model.
PREFERRED_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gpt-4o-mini",
    "claude-haiku-4.5",
    "claude-sonnet-4.5",
    "openai/gpt-4o-mini",
    "google/gemini-3.5-flash",
    "sonar",
    "command-a-03-2025",
]

DEPRECATED_MODELS = {
    "gemini-2.5-flash",
    "google/gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "google/gemini-2.5-flash-lite-preview-06-17",
}

# Model names matching these are not chat models; never auto-select them.
_NON_CHAT_MARKERS = ("embedding", "whisper", "dall-e", "gpt-image", "tts", "image", "alternate")

# Hub builder tools (huf.ai.tools.builder, synced by the tool registry on
# after_migrate) that let the hub chat create tables/agents/tools/prompts.
BUILDER_TOOL_NAMES = (
    "create_huf_table",
    "list_table_rows",
    "add_table_row",
    "update_table_row",
    "delete_table_row",
    "draft_agent",
    "update_agent_prompt",
    "attach_agent_tools",
    "publish_agent",
    "create_agent_tool",
    "list_provider_options",
    "ask_user",
    "list_agents",
    "get_agent",
    "list_apps",
    "get_app",
    "draft_app",
    "update_app",
    "install_app",
    "list_app_components",
    "render_app_component",
)


def _attach_builder_tools(agent) -> bool:
    """Attach hub builder tools to the orchestrator doc, idempotently.

    Only attaches tools already synced into Agent Tool Function records
    (tool sync runs before seeding on after_migrate). Returns True if any
    tool was added.
    """
    existing = {row.tool for row in agent.get("agent_tool") or []}
    added = False
    for tool_name in BUILDER_TOOL_NAMES:
        if tool_name not in existing and frappe.db.exists("Agent Tool Function", tool_name):
            agent.append("agent_tool", {"tool": tool_name})
            added = True
    return added


def ensure_hub_orchestrator_tools() -> bool:
    """Attach builder tools to an existing Hub Orchestrator. Idempotent."""
    if not frappe.db.exists("Agent", HUB_AGENT_NAME):
        return False
    agent = frappe.get_doc("Agent", HUB_AGENT_NAME)
    if not _attach_builder_tools(agent):
        return False
    with _seeding_flag():
        agent.save(ignore_permissions=True)
    logger.info("Hub Orchestrator builder tools attached.")
    return True


@contextmanager
def _seeding_flag():
    """Set frappe.flags.in_seeding so the Agent is_system guards pass, then restore."""
    previous = getattr(frappe.flags, "in_seeding", False)
    frappe.flags.in_seeding = True
    try:
        yield
    finally:
        frappe.flags.in_seeding = previous


def _seed_path() -> Path:
    return Path(frappe.get_app_path("huf")) / "huf" / "agents" / SEED_FILE


def _load_seed_data() -> dict:
    with open(_seed_path(), encoding="utf-8") as f:
        return json.load(f)


def _provider_has_key(provider_name) -> bool:
    """True only if the provider exists and has an api_key. Never logs/returns the value."""
    if not provider_name or not frappe.db.exists("AI Provider", provider_name):
        return False
    try:
        return bool(frappe.get_doc("AI Provider", provider_name).get_password("api_key"))
    except frappe.ValidationError:
        # Frappe raises "Password not found" when no password row exists at all.
        return False


def _find_keyed_provider():
    """First AI Provider (by creation) that has an api_key set, else None."""
    for name in frappe.get_all("AI Provider", pluck="name", order_by="creation asc"):
        if _provider_has_key(name):
            return name
    return None


def _default_model_for_provider(provider_name):
    """Sensible default chat model for a provider from existing AI Model records."""
    models = frappe.get_all(
        "AI Model",
        filters={"provider": provider_name},
        pluck="name",
        order_by="creation asc",
    )
    if not models:
        return None
    for preferred in PREFERRED_MODELS:
        if preferred in models:
            return preferred
    for model in models:
        if not any(marker in model.lower() for marker in _NON_CHAT_MARKERS):
            return model
    return None


def _fallback_provider_model():
    """
    Provider/model to store when nothing has a key yet. Mirrors the
    demo-assistant convention (OpenAI + gpt-4o-mini) so the record passes
    Link and mandatory validation while staying disabled.
    """
    if frappe.db.exists("AI Provider", "OpenAI") and frappe.db.exists("AI Model", "gpt-4o-mini"):
        return "OpenAI", "gpt-4o-mini"
    providers = frappe.get_all("AI Provider", pluck="name", order_by="creation asc", limit=1)
    if providers:
        model = _default_model_for_provider(providers[0])
        if model:
            return providers[0], model
    return None, None


def create_hub_orchestrator_agent() -> bool:
    """
    Idempotently seed the Hub Orchestrator system agent.

    - Skips creation if the agent already exists, but still tries to fix a
      broken provisioning (provider without a key / no model) when a keyed
      provider is available.
    - Picks the first AI Provider with an api_key plus its default model.
    - If no provider has a key yet, seeds the agent disabled=1 (with the
      demo-assistant-style placeholder provider so validation passes); it is
      enabled automatically once a provider key is saved.

    Returns True if the agent was created.
    """
    if frappe.db.exists("Agent", HUB_AGENT_NAME):
        provision_hub_orchestrator()
        ensure_hub_orchestrator_tools()
        return False

    seed = _load_seed_data()
    doc = frappe.get_doc({"doctype": "Agent", **seed})

    provider_name = _find_keyed_provider()
    model = _default_model_for_provider(provider_name) if provider_name else None

    if provider_name and model:
        doc.provider = provider_name
        doc.model = model
        doc.disabled = 0
    else:
        fallback_provider, fallback_model = _fallback_provider_model()
        if fallback_provider and fallback_model:
            doc.provider = fallback_provider
            doc.model = fallback_model
        else:
            # No provider/model records at all: insert anyway so the locked
            # record exists; bypass the mandatory check like install.py does.
            doc.flags.ignore_mandatory = True
        doc.disabled = 1
        logger.info(
            "Hub Orchestrator seeded disabled: no AI Provider has an API key yet. "
            "It will be enabled automatically when a provider key is saved."
        )

    doc.source_app = "huf"
    doc.source_file = f"huf/agents/{SEED_FILE}"
    _attach_builder_tools(doc)
    with _seeding_flag():
        doc.insert(ignore_permissions=True)
    logger.info(f"Hub Orchestrator agent seeded (disabled={doc.disabled}).")
    return True


def provision_hub_orchestrator(provider_doc=None) -> bool:
    """Assign a usable provider/model pair to Hub Orchestrator if unconfigured."""
    if not frappe.db.exists("Agent", HUB_AGENT_NAME):
        return False

    agent = frappe.get_doc("Agent", HUB_AGENT_NAME)
    if (
        agent.provider
        and agent.model
        and _provider_has_key(agent.provider)
        and agent.model not in DEPRECATED_MODELS
    ):
        return False

    if provider_doc is not None and provider_doc.get_password("api_key", raise_exception=False):
        provider_name = provider_doc.name
    else:
        provider_name = _find_keyed_provider()
    if not provider_name:
        return False

    model = _default_model_for_provider(provider_name)
    if not model:
        return False

    agent.provider = provider_name
    agent.model = model
    agent.disabled = 0
    with _seeding_flag():
        agent.save(ignore_permissions=True)
    logger.info(f"Hub Orchestrator provisioned with provider '{provider_name}' and model '{model}'.")
    return True


def on_ai_provider_update(doc, method=None):
    """doc_events hook: when an AI Provider is saved with an api_key, make sure
    Hub Orchestrator can use it (re-provision if it had no usable provider)."""
    try:
        if doc.get_password("api_key", raise_exception=False):
            provision_hub_orchestrator(provider_doc=doc)
    except Exception as e:
        frappe.log_error(f"Hub Orchestrator re-provisioning failed: {e}", "Hub Orchestrator")
