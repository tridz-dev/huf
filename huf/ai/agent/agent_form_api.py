"""Backend support for the redesigned Agent form (Track-Item: AF-1).

- Workspace default model (stored in the Agent Settings single: ``default_provider`` /
  ``default_model``, which already exist, so no schema change).
- Draft-override test run: run an agent with unsaved editor values applied in memory only.
- Delete pre-check: linked-record counts so the UI can offer Archive instead of Delete.

Archive and hard delete reuse ``huf.huf.doctype.agent.agent.archive_agent`` (agent.edit
capability or owner) and ``delete_agent_cascade`` (System Manager only).
"""

import time

import frappe
from frappe import _

# Names containing these are not chat models (mirrors app_seeding.hub_orchestrator).
_NON_CHAT_MARKERS = ("embedding", "whisper", "dall-e", "gpt-image", "tts", "image", "alternate")
_CHAT_MODALITIES = {"", "text", "vision"}



DRAFT_OVERRIDE_FIELDS = ("instructions", "provider", "model", "temperature", "top_p", "agent_tool")


def apply_draft_overrides(agent_doc, draft_overrides):
    """Apply whitelisted editor-draft overrides onto an in-memory Agent doc (never saved).

    ``agent_tool`` is a list of Agent Tool Function names that replaces the tool rows.
    Unknown keys are ignored so a draft can never touch permissions or run budgets.
    """
    if not draft_overrides:
        return agent_doc
    for key in ("instructions", "provider", "model", "temperature", "top_p"):
        if key in draft_overrides and draft_overrides[key] not in (None, ""):
            setattr(agent_doc, key, draft_overrides[key])
    if draft_overrides.get("instructions"):
        agent_doc.prompt_mode = "Local"
    if "agent_tool" in draft_overrides and draft_overrides["agent_tool"] is not None:
        existing = {row.tool: row for row in (agent_doc.get("agent_tool") or [])}
        agent_doc.set("agent_tool", [])
        for name in draft_overrides["agent_tool"]:
            row = existing.get(name)
            data = {"tool": name}
            if row:
                skip = {"name", "parent", "parenttype", "parentfield", "idx", "creation",
                        "modified", "modified_by", "owner", "docstatus", "doctype"}
                data = {k: v for k, v in row.as_dict().items() if k not in skip}
            agent_doc.append("agent_tool", data)
    return agent_doc


def _assert_logged_in():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."), frappe.PermissionError)


def _is_system_manager() -> bool:
    return "System Manager" in (frappe.get_roles(frappe.session.user) or [])


def _is_chat_model(row) -> bool:
    name = (row.get("model_name") or row.get("name") or "").lower()
    if any(marker in name for marker in _NON_CHAT_MARKERS):
        return False
    modalities = {m.strip().lower() for m in (row.get("modalities") or "").split(",")}
    return bool(modalities & _CHAT_MODALITIES) or modalities == {""}


@frappe.whitelist()
def get_workspace_default_model() -> dict:
    """Return ``{provider, model}``: the saved default, else the first chat-capable model."""
    _assert_logged_in()
    if not frappe.has_permission("Agent", "read"):
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    provider = frappe.db.get_single_value("Agent Settings", "default_provider")
    model = frappe.db.get_single_value("Agent Settings", "default_model")
    if provider and model:
        model_provider = frappe.db.get_value("AI Model", model, "provider")
        if model_provider:
            return {"provider": provider if provider == model_provider else model_provider, "model": model}
    if model:
        model_provider = frappe.db.get_value("AI Model", model, "provider")
        if model_provider:
            return {"provider": model_provider, "model": model}

    rows = frappe.get_all(
        "AI Model",
        fields=["name", "model_name", "provider", "modalities"],
        order_by="creation asc",
        limit=200,
    )
    for row in rows or []:
        if row.get("provider") and _is_chat_model(row):
            return {"provider": row["provider"], "model": row["name"]}
    return {"provider": None, "model": None}


@frappe.whitelist(methods=["POST"])
def set_workspace_default_model(provider: str = None, model: str = None) -> dict:
    """Save the workspace default model (System Manager only)."""
    if not _is_system_manager():
        frappe.throw(_("Only System Manager may set the workspace default model."), frappe.PermissionError)
    if not model:
        frappe.throw(_("Model is required."), frappe.ValidationError)
    model_provider = frappe.db.get_value("AI Model", model, "provider")
    if not model_provider:
        frappe.throw(_("AI Model '{0}' was not found.").format(model), frappe.ValidationError)
    if provider and provider != model_provider:
        frappe.throw(_("Model '{0}' does not belong to provider '{1}'.").format(model, provider), frappe.ValidationError)
    frappe.db.set_single_value(
        "Agent Settings", {"default_provider": model_provider, "default_model": model}
    )
    return {"provider": model_provider, "model": model}


def _clean_overrides(draft_overrides) -> dict:
    if isinstance(draft_overrides, str):
        draft_overrides = frappe.parse_json(draft_overrides) if draft_overrides.strip() else {}
    if not draft_overrides:
        return {}
    if not isinstance(draft_overrides, dict):
        frappe.throw(_("draft_overrides must be an object."), frappe.ValidationError)
    cleaned = {k: draft_overrides[k] for k in DRAFT_OVERRIDE_FIELDS if k in draft_overrides}
    for key in ("temperature", "top_p"):
        if cleaned.get(key) not in (None, ""):
            try:
                cleaned[key] = float(cleaned[key])
            except (TypeError, ValueError):
                frappe.throw(_("{0} must be a number.").format(key), frappe.ValidationError)
    if "agent_tool" in cleaned:
        tools = cleaned["agent_tool"]
        if isinstance(tools, str):
            tools = frappe.parse_json(tools)
        if tools is None:
            tools = []
        if not isinstance(tools, (list, tuple)) or not all(isinstance(t, str) for t in tools):
            frappe.throw(_("agent_tool must be a list of tool names."), frappe.ValidationError)
        for name in tools:
            if not frappe.db.exists("Agent Tool Function", name):
                frappe.throw(_("Tool '{0}' was not found.").format(name), frappe.ValidationError)
        cleaned["agent_tool"] = list(tools)
    return cleaned


@frappe.whitelist(methods=["POST"])
def run_agent_draft_test(agent_name: str, prompt: str, draft_overrides=None) -> dict:
    """Run a saved agent once with unsaved draft values applied in memory (never saved).

    Requires write access to the agent (agent.edit capability). Non-streaming.
    """
    if not agent_name or not prompt:
        frappe.throw(_("Agent Name and prompt are required."), frappe.ValidationError)
    agent_doc = frappe.get_doc("Agent", agent_name)
    agent_doc.check_permission("write")
    overrides = _clean_overrides(draft_overrides)
    if not frappe.has_permission("Agent Run", "create"):
        frappe.throw(_("You do not have permission to create an Agent Run."), frappe.PermissionError)

    from huf.ai.agent.integration import (
        ConversationManager,
        _execute_agent_run,
        _resolve_effective_model,
        _next_run_sequence,
    )

    draft_doc = apply_draft_overrides(frappe.get_doc("Agent", agent_name), overrides)
    provider, model, _model_name = _resolve_effective_model(
        draft_doc, model=overrides.get("model"), provider=overrides.get("provider")
    )

    channel = "draft_test"
    conv_manager = ConversationManager(agent_name=agent_name, channel=channel, external_id=None)
    conversation = conv_manager.create_new_conversation(title=f"Draft test of {agent_name}")
    conv_manager.add_message(conversation, "user", prompt, provider, model, agent_name, None)

    run_doc = frappe.get_doc({
        "doctype": "Agent Run",
        "agent": agent_name,
        "status": "Started",
        "conversation": conversation.name,
        "prompt": prompt,
        "model": model,
        "provider": provider,
        "sequence": _next_run_sequence(conversation.name),
        "run_kind": "draft_test",
    })
    run_doc.insert()

    started = time.monotonic()
    result = _execute_agent_run(
        agent_name=agent_name,
        run_id=run_doc.name,
        conversation_id=conversation.name,
        prompt=prompt,
        provider=provider,
        model=model,
        channel_id=channel,
        skip_user_message=True,
        draft_overrides=overrides,
    ) or {}
    latency_ms = int((time.monotonic() - started) * 1000)

    run = frappe.db.get_value(
        "Agent Run",
        run_doc.name,
        ["status", "response", "error_message", "input_tokens", "output_tokens", "total_tokens"],
        as_dict=True,
    ) or {}
    calls = frappe.get_all(
        "Agent Tool Call",
        filters={"agent_run": run_doc.name},
        fields=["tool", "tool_args", "tool_result", "status", "error_message"],
        order_by="creation asc",
    )
    return {
        "success": run.get("status") == "Success",
        "response": run.get("response") or result.get("response"),
        "error": run.get("error_message"),
        "agent_run_id": run_doc.name,
        "conversation_id": conversation.name,
        "tool_calls": calls,
        "latency_ms": latency_ms,
        "tokens": {
            "input": run.get("input_tokens"),
            "output": run.get("output_tokens"),
            "total": run.get("total_tokens"),
        },
    }


@frappe.whitelist()
def get_agent_delete_precheck(agent_name: str) -> dict:
    """Counts of records linked to an agent, plus what the UI may offer."""
    doc = frappe.get_doc("Agent", agent_name)
    doc.check_permission("read")
    counts = {
        "conversations": frappe.db.count("Agent Conversation", {"agent": agent_name}),
        "runs": frappe.db.count("Agent Run", {"agent": agent_name}),
        "automations": frappe.db.count("Automation", {"agent": agent_name}),
        "triggers": frappe.db.count("Agent Trigger", {"agent": agent_name}),
    }
    linked = any(counts.values())
    from huf.permissions import has_capability

    user = frappe.session.user
    can_archive = bool(has_capability(user, "agent.edit") or doc.owner == user)
    can_delete = _is_system_manager()
    return {
        "agent": agent_name,
        "counts": counts,
        "has_linked": linked,
        "disabled": bool(doc.disabled),
        "can_delete": can_delete,
        "can_archive": can_archive,
        "suggest_archive": linked and can_archive,
        "archive_method": "huf.huf.doctype.agent.agent.archive_agent",
        "delete_method": "huf.huf.doctype.agent.agent.delete_agent_cascade",
    }
