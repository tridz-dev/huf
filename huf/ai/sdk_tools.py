import asyncio
import inspect
import json
import re
from collections.abc import Callable
from typing import Any

import frappe
from agents import FunctionTool
from frappe import _

from huf.ai.conversation_data_tools import *
from huf.ai.conversation_data_tools import _load_state
from huf.ai.handlers.agent_runner import *

# Re-export handler functions so existing function_path strings and imports keep working.
from huf.ai.handlers.crud import *

# Explicit re-exports for underscore-prefixed helpers used by other modules/tests.
from huf.ai.handlers.crud import _sanitize_for_doctype
from huf.ai.handlers.media import *
from huf.ai.handlers.media import _resolve_tts_config
from huf.ai.tool_invocation import (
    CLIENT_SIDE_TOOL_FUNCTION_PATH,
    CLIENT_SIDE_TOOL_TYPE,
    DYNAMIC_FUNCTION_PATH_TYPES,
    TYPE_TO_FUNCTION_PATH,
    build_extra_args,
)
from huf.ai.tool_invocation import (
    check_tool_permission as _check_tool_permission,
)
from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.tool_types import _GUEST_DOCTYPE_PINNED_TYPES, _GUEST_REPORT_PINNED_TYPES
from huf.ai.tools.perplexity import handle_perplexity_search

logger = frappe.logger("huf")


def _frappe_run_context_dict(ctx) -> dict:
    """Huf run context may be a dict or an Agents SDK ToolContext wrapping that dict."""
    if ctx is None:
        return {}
    if isinstance(ctx, dict):
        return ctx
    inner = getattr(ctx, "context", None)
    return inner if isinstance(inner, dict) else {}


def _merge_run_context(args_dict: dict, ctx) -> dict:
    """Inject run-context values into tool args without clobbering the LLM's.

    conversation_id / agent_run_id / agent_name from the huf run context are
    only injected when the key is NOT already present in args_dict — the
    LLM's explicit arguments always win (setdefault semantics).

    ``call_id`` is the Agents SDK's own tool_call_id (``ctx.tool_call_id``,
    e.g. ``call_xyz``) rather than anything from the huf run context dict —
    it identifies this specific invocation, which tool functions that create
    their own audit row up front (e.g. client-side tools, code execution)
    need in order to correlate a later result back to this call.
    """
    huf_ctx = _frappe_run_context_dict(ctx)
    for key in ("conversation_id", "agent_run_id", "agent_name"):
        if key not in huf_ctx:
            continue

        # A BLANK value counts as absent, not as the LLM's choice.
        #
        # This used to be a plain setdefault, which only fills a key that is
        # missing entirely. Models routinely emit the key with an empty
        # string for ids they cannot know - observed live: gemini sent
        # {"conversation_id": ""} to list_document_artifacts, setdefault saw
        # the key present and kept "", and the tool failed with
        # "'conversation_id' is required" even though the run context had the
        # real id the whole time. The agent then told the user the action had
        # succeeded. Every context-injected tool was exposed to this, not
        # just the document ones.
        current = args_dict.get(key)
        if current is None or (isinstance(current, str) and not current.strip()):
            args_dict[key] = huf_ctx[key]

    tool_call_id = getattr(ctx, "tool_call_id", None)
    if tool_call_id:
        args_dict.setdefault("call_id", tool_call_id)

    return args_dict


def _pin_run_identity(args_dict: dict, ctx, nonce: str = None) -> dict:
    """Overwrite (never default) the run identity args from the server-side run context.

    Used by tools that must not trust the model for who/what run they act on
    (Desktop Workspace tools): ``agent_run_id`` and ``conversation_id`` come only from
    the run context, and ``call_id`` is derived deterministically from the run and the
    SDK ``tool_call_id`` so a redelivered or retried call dedupes. Anything the model
    sent for these keys is discarded.
    """
    from huf.ai.desktop_executor import derive_call_id

    huf_ctx = _frappe_run_context_dict(ctx)
    for key in ("agent_run_id", "conversation_id"):
        args_dict.pop(key, None)
        if huf_ctx.get(key):
            args_dict[key] = huf_ctx[key]
    args_dict.pop("call_id", None)
    args_dict.pop("_dx_pin", None)  # minted below by the caller, never taken from the model
    tool_call_id = getattr(ctx, "tool_call_id", None)
    if tool_call_id and args_dict.get("agent_run_id"):
        args_dict["call_id"] = derive_call_id(args_dict["agent_run_id"], tool_call_id, nonce)
    # The exact LLM-issued id, sent on its own so the desktop can join its feed to the chat row.
    args_dict.pop("tool_call_id", None)
    if tool_call_id and isinstance(tool_call_id, str):
        args_dict["tool_call_id"] = tool_call_id[:256]
    return args_dict


# _check_tool_permission moved to huf.ai.tool_invocation.check_tool_permission
# (T-10) so the deterministic tool path shares the same guest/mutating-type
# gate; imported above as _check_tool_permission to keep this call site
# unchanged. The old signature accepted an unused `context` positional arg
# -- dropped, see the call site below.


# Tools that must always be built eagerly for a lazy-discovery agent: the
# discovery tools themselves (without them the agent could never unlock
# anything else) plus the small set of always-on utility tools.
_LAZY_DISCOVERY_TOOL_NAMES = {"list_tool_groups", "search_tools", "describe_tool_group", "load_tools"}
_LAZY_DISCOVERY_ALWAYS_EAGER_TOOL_NAMES = _LAZY_DISCOVERY_TOOL_NAMES | {
    "get_conversation_data", "set_conversation_data", "load_conversation_data",
    "ask_user", "get_result_context",
}


def _get_lazy_discovered_tool_names(kwargs: dict) -> set:
    """Tool names already unlocked via lazy discovery for the current conversation.

    Fails safe (empty set) whenever no conversation context is available or
    conversation_data can't be read, so lazy-tool agents never break outside
    a conversation run (e.g. no conversation_id in this run context yet).
    """
    conversation_id = (kwargs or {}).get("conversation_id")
    if not conversation_id:
        return set()

    try:
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)
        for item in state["items"]:
            if item.get("name") == "_lazy_tools":
                discovered = (item.get("value") or {}).get("discovered") or []
                return set(discovered)
    except Exception as e:
        logger.debug(f"Could not resolve lazy-discovered tools for {conversation_id}: {e!s}")
        return set()

    return set()


def _is_desktop_workspace_tool_doc(function_doc) -> bool:
    """True for an Agent Tool Function row that is one of the Desktop Workspace tools."""
    from huf.ai.tools._registry import DESKTOP_WORKSPACE_TOOL_NAMES

    return (function_doc.tool_name or "") in DESKTOP_WORKSPACE_TOOL_NAMES or (
        function_doc.function_path or ""
    ).startswith("huf.ai.tools.desktop_workspace.")


def _desktop_tool_group(function_doc):
    """Which desktop tool group an Agent Tool Function row belongs to, or None.

    ``"workspace"``, ``"skills"``, ``"processes"`` and ``"mcp"`` (local MCP and browser grants)
    are built; ``"unknown"`` is a row whose handler lives in a ``desktop_*`` module this server
    does not know how to expose (never built: fail closed).
    """
    from huf.ai.tools._registry import (
        DESKTOP_LOCAL_MCP_TOOL_NAMES,
        DESKTOP_LOCAL_SKILL_TOOL_NAMES,
        DESKTOP_PROCESS_TOOL_NAMES,
    )

    name = function_doc.tool_name or ""
    path = function_doc.function_path or ""
    if _is_desktop_workspace_tool_doc(function_doc):
        return "workspace"
    if name in DESKTOP_LOCAL_SKILL_TOOL_NAMES:
        return "skills"
    if name in DESKTOP_PROCESS_TOOL_NAMES:
        return "processes"
    if name in DESKTOP_LOCAL_MCP_TOOL_NAMES:
        return "mcp"
    if path.startswith("huf.ai.tools.desktop_"):
        return "unknown"
    return None


def _is_desktop_tool_doc(function_doc) -> bool:
    """True for any row that may only be exposed to a run pinned to a live desktop."""
    return _desktop_tool_group(function_doc) is not None


# The desktop_skill_read description carries the catalog: at most this many entries and this
# many characters (about 3k tokens), whichever comes first (PLAN 4.4).
SKILL_CATALOG_MAX_ENTRIES = 40
SKILL_CATALOG_MAX_CHARS = 12_000


def _attached_server_skill_names(agent) -> set:
    """Normalised names of the ACTIVE server skills attached to ``agent`` (server skills win)."""
    from huf.ai.desktop_executor import normalize_catalog_name

    names = set()
    try:
        for row in agent.get("agent_skill", []) or []:
            skill_name, status = frappe.db.get_value("Skill", row.skill, ["skill_name", "status"]) or (None, None)
            if skill_name and (status or "Active") == "Active":
                names.add(normalize_catalog_name(skill_name))
    except Exception as e:
        frappe.logger("huf").debug(f"Could not read attached server skills: {e!s}")
    names.discard("")
    return names


def _skill_read_description(base: str, visible: list) -> str:
    """The base description plus the (capped, re-sanitised) local skill catalog."""
    from huf.ai.desktop_executor import SKILL_DESCRIPTION_MAX_CHARS, sanitize_text

    lines, used = [], 0
    for entry in visible:
        if len(lines) >= SKILL_CATALOG_MAX_ENTRIES:
            break
        line = f"- {entry['id']}: {sanitize_text(entry.get('description'), SKILL_DESCRIPTION_MAX_CHARS)}"
        if entry.get("has_scripts"):
            line += " [has scripts]"
        if used + len(line) > SKILL_CATALOG_MAX_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    out = [base, "", f"Skills the user enabled on their computer ({len(lines)} of {len(visible)} shown):"]
    out.extend(lines)
    if len(lines) < len(visible):
        out.append(
            f"{len(visible) - len(lines)} more skills are enabled: use desktop_skill_list to search them."
        )
    return "\n".join(out)


def _build_desktop_tools(function_docs, desktop_ctx, agent=None) -> list:
    """Build the attached desktop tool groups for a run pinned to a live executor.

    Returns [] unless desktop_ctx carries an executor_id whose lease is live and
    owned by the ctx user (huf.ai.desktop_executor.resolve_desktop_ctx). The
    pinned _dx_* values come from the server-side lease, and overwrite anything
    the LLM passes (extra_args are applied after the LLM's args).

    Groups (PLAN 4.3): ``workspace`` needs only the live lease. ``skills`` (local skills)
    additionally needs, per tool, the lease capability (``skills.read`` / ``skills.exec``) and a
    catalog PINNED to the run (``desktop_ctx['catalog_hash']``, never the lease's current one)
    that names at least one enabled skill (one with scripts for ``desktop_skill_run``).
    ``processes`` needs the ``proc`` capability. ``mcp`` (local MCP servers, ``desktop_local_mcp``,
    ``desktop_mcp_find``/``desktop_mcp_call``, and the ``desktop_browser`` grant) is expanded from
    the pinned catalog by :func:`_build_local_mcp_tools`.
    """
    if not desktop_ctx or not isinstance(desktop_ctx, dict):
        return []
    executor_id = desktop_ctx.get("executor_id")
    if not executor_id:
        return []

    try:
        from huf.ai.desktop_executor import is_lease_live, resolve_desktop_ctx

        if not is_lease_live(executor_id):
            return []
        live = resolve_desktop_ctx(executor_id, user=desktop_ctx.get("user") or None)
    except Exception as e:
        frappe.logger("huf").debug(f"Desktop lease check failed: {e!s}")
        return []
    if not live or not live.get("executor_id") or not live.get("user"):
        return []

    # The fingerprint is the one pinned on the run at send time, NOT the live lease's:
    # a queued run sent under workspace A must not silently operate on workspace B.
    extra_args = {
        "_dx_executor_id": live["executor_id"],
        "_dx_fingerprint": desktop_ctx.get("fingerprint") or live.get("fingerprint") or "",
        "_dx_user": live["user"],
        # Pinned from the agent document (never model-controlled): the doc PK for policy matching
        # and the display name the desktop approval window shows.
        "_dx_agent": (getattr(agent, "name", None) or getattr(agent, "agent_name", None) or "") if agent is not None else "",
        "_dx_agent_display": (getattr(agent, "agent_name", None) or "") if agent is not None else "",
    }

    # The agent's desktop access ceiling: a capability that is ``off`` removes its tools from the
    # model's list. The pinned (signed) policy wins; an unpinned ctx reads it from the agent.
    from huf.ai import desktop_policy

    policy = desktop_policy.sanitize_policy(desktop_ctx.get("agent_policy"))
    if policy is None:
        policy = desktop_policy.policy_from_agent(agent)

    skills_state = None  # (capabilities, visible skills, hidden ids), computed on first use
    lease_caps = None
    built = []
    seen = set()
    mcp_docs = []
    for function_doc in function_docs:
        if function_doc.tool_name in seen:
            continue
        if not desktop_policy.tool_allowed(policy, function_doc.tool_name):
            continue
        group = _desktop_tool_group(function_doc)
        if group == "mcp":
            mcp_docs.append(function_doc)
            continue
        if group not in ("workspace", "skills", "processes"):
            continue
        description = function_doc.description
        tool_extra = dict(extra_args)
        if group == "processes":
            from huf.ai.desktop_executor import lease_capabilities
            from huf.ai.tools._registry import DESKTOP_PROCESS_CAPABILITY

            if lease_caps is None:
                lease_caps = lease_capabilities(executor_id)
            if DESKTOP_PROCESS_CAPABILITY not in lease_caps:
                continue
        if group == "skills":
            if skills_state is None:
                skills_state = _local_skills_state(desktop_ctx, executor_id, agent)
            caps, visible, hidden = skills_state
            from huf.ai.tools._registry import DESKTOP_LOCAL_SKILL_CAPABILITY

            needed = DESKTOP_LOCAL_SKILL_CAPABILITY.get(function_doc.tool_name)
            if not needed or needed not in caps or not visible:
                continue
            if function_doc.tool_name == "desktop_skill_run" and not any(
                e.get("has_scripts") for e in visible
            ):
                continue
            if function_doc.tool_name == "desktop_skill_read":
                description = _skill_read_description(function_doc.description or "", visible)
            tool_extra["_dx_hidden_skills"] = list(hidden)
        try:
            params = json.loads(function_doc.params) if function_doc.params else {}
            params.pop("additionalProperties", None)
            tool = create_function_tool(
                function_doc.tool_name,
                description,
                function_doc.function_path,
                params,
                extra_args=tool_extra,
                tool_type=function_doc.types,
                blocking=True,
                pin_run_context=True,
            )
            if tool:
                built.append(tool)
                seen.add(function_doc.tool_name)
        except Exception as e:
            frappe.logger("huf").debug(f"Error wiring desktop tool {function_doc.tool_name}: {e!s}")
    if mcp_docs:
        built.extend(
            _build_local_mcp_tools(mcp_docs, desktop_ctx, executor_id, agent, extra_args, seen, policy=policy)
        )
    return built


_MCP_TOOL_HANDLER = "huf.ai.tools.desktop_local.handle_mcp_tool_call"


def _spec_parameters_schema(spec) -> dict:
    """JSON schema for a registry spec's ``parameters`` list (used for the find/call tools that a
    grant expands to, which are not necessarily attached as rows)."""
    props, required = {}, []
    for p in spec.get("parameters") or []:
        prop = {"type": p["type"], "description": p.get("description", "")}
        if p["type"] == "array":
            from huf.ai.tools._registry import array_items_schema

            prop["items"] = array_items_schema(p["fieldname"])
        props[p["fieldname"]] = prop
        if p.get("required"):
            required.append(p["fieldname"])
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _build_local_mcp_tools(mcp_docs, desktop_ctx, executor_id, agent, extra_args, seen, policy=None) -> list:
    """The local MCP and browser groups (PLAN 4.3, 4.4, 4.8).

    ``desktop_local_mcp`` expands to ``lmcp__<server>__<tool>`` tools within the eager budget and,
    when tools remain, to ``desktop_mcp_find`` + ``desktop_mcp_call``; those two are also built
    when their own rows are attached. ``desktop_browser`` expands to the curated browser subset.
    Everything is built from the catalog PINNED to the run and needs the lease capabilities in
    ``DESKTOP_LOCAL_MCP_CAPABILITY``. The agent name, server and tool of every tool are pinned
    here (``_dx_*`` overwrite whatever the model sends).
    """
    from huf.ai import desktop_mcp
    from huf.ai.desktop_executor import get_catalog, lease_capabilities, sanitize_text
    from huf.ai.tools._registry import DESKTOP_LOCAL_MCP_CAPABILITY, DESKTOP_LOCAL_MCP_TOOLS

    catalog = get_catalog(executor_id, desktop_ctx.get("catalog_hash"))
    if not catalog:
        return []
    caps = set(lease_capabilities(executor_id))
    attached = {d.tool_name: d for d in mcp_docs}
    agent_name = (getattr(agent, "name", None) or getattr(agent, "agent_name", None)) if agent is not None else None
    base_extra = {
        **extra_args,
        "_dx_agent": agent_name or "",
        "_dx_agent_display": (getattr(agent, "agent_name", None) or "") if agent is not None else "",
    }
    specs = {t["tool_name"]: t for t in DESKTOP_LOCAL_MCP_TOOLS}
    built = []

    def allowed(name):
        from huf.ai import desktop_policy

        return set(DESKTOP_LOCAL_MCP_CAPABILITY[name]) <= caps and desktop_policy.tool_allowed(policy, name)

    def add(tool):
        if tool and tool.name not in seen:
            built.append(tool)
            seen.add(tool.name)

    def dynamic(spec, kind):
        try:
            return create_function_tool(
                spec["name"],
                spec["description"],
                _MCP_TOOL_HANDLER,
                spec["schema"],
                extra_args={
                    **base_extra,
                    "_dx_mcp_server": spec["server"],
                    "_dx_mcp_tool": spec["tool"],
                    "_dx_mcp_kind": kind,
                },
                blocking=True,
                pin_run_context=True,
            )
        except Exception as e:
            frappe.logger("huf").debug(f"Error wiring local MCP tool {spec.get('name')}: {e!s}")
            return None

    def fixed(name):
        spec = specs[name]
        try:
            return create_function_tool(
                name,
                spec["description"],
                spec["function_path"],
                _spec_parameters_schema(spec),
                extra_args=base_extra,
                blocking=True,
                pin_run_context=True,
            )
        except Exception as e:
            frappe.logger("huf").debug(f"Error wiring desktop tool {name}: {e!s}")
            return None

    plan = None
    if ("desktop_local_mcp" in attached and allowed("desktop_local_mcp")) or any(
        n in attached and allowed(n) for n in ("desktop_mcp_find", "desktop_mcp_call")
    ):
        plan = desktop_mcp.plan_mcp_group(catalog, agent_name, sanitize_text)
    if plan is not None:
        grant = "desktop_local_mcp" in attached and allowed("desktop_local_mcp")
        if grant:
            for spec in plan["eager"]:
                add(dynamic(spec, "mcp"))
        has_tools = bool(plan["eager"] or plan["overflow"])
        for name in ("desktop_mcp_find", "desktop_mcp_call"):
            if not has_tools:
                continue
            if (grant and plan["overflow"]) or (name in attached and allowed(name)):
                add(fixed(name))

    if "desktop_browser" in attached and allowed("desktop_browser"):
        for spec in desktop_mcp.plan_browser_group(catalog, agent_name, sanitize_text):
            add(dynamic(spec, "browser"))
    return built


def _local_skills_state(desktop_ctx, executor_id, agent):
    """``(lease capabilities, visible catalog skills, shadowed skill ids)`` for the skills group.

    Empty visible list when no catalog is pinned, the pinned catalog expired, or every local
    skill is shadowed by an attached server skill of the same name.
    """
    from huf.ai.desktop_executor import get_catalog, lease_capabilities

    caps = lease_capabilities(executor_id)
    catalog = get_catalog(executor_id, desktop_ctx.get("catalog_hash"))
    if not catalog:
        return caps, [], []
    server_names = _attached_server_skill_names(agent) if agent is not None else set()
    visible, hidden = [], []
    for entry in catalog.get("skills") or []:
        (hidden if entry.get("name") in server_names else visible).append(entry)
    return caps, visible, [e["id"] for e in hidden]


# Backwards-compatible name: the workspace group is the first group of ``_build_desktop_tools``.
_build_desktop_workspace_tools = _build_desktop_tools


def create_agent_tools(agent, model_name: str = None, desktop_ctx: dict | None = None, **kwargs) -> list[FunctionTool]:
    """
    Create function tools for Huf Agent

    This combines:
    1. MCP tools from linked MCP servers
    2. Native tools from Agent Tool Function documents

    model_name is the effective AI Model in use for this run (falls back to
    agent.model when omitted) — passed through to the permission-aware
    registry so an AI Model's capability overrides (see huf.ai.capability_discovery)
    can gate tools like ask_user regardless of the agent's own setting.

    When agent.enable_lazy_tools is set, native tools not yet unlocked via the
    lazy-discovery flow (see huf.ai.tools.lazy_discovery) are skipped entirely
    instead of being built, to save tokens on the tool schema payload sent to
    the model. This is gated on kwargs["conversation_id"]; callers that don't
    pass one get the fail-safe (nothing discovered yet) rather than an error.

    desktop_ctx is the run's pinned Huf Desktop executor
    ({executor_id, fingerprint, user, label}) or None. Desktop Workspace tools
    (huf.ai.tools._registry.DESKTOP_WORKSPACE_TOOLS) are exposed only when the
    agent has them attached (ordinary Agent Tool rows) AND desktop_ctx names an
    executor whose lease is live; otherwise they are absent from the schema.
    """
    tools = []
    lazy_enabled = bool(getattr(agent, "enable_lazy_tools", False))
    discovered_tool_names = _get_lazy_discovered_tool_names(kwargs) if lazy_enabled else set()

    # Load MCP tools from linked MCP servers
    if hasattr(agent, "agent_mcp_server") and agent.agent_mcp_server:
        try:
            from huf.ai.mcp_client import create_mcp_tools
            mcp_tools = create_mcp_tools(agent)
            tools.extend(mcp_tools)
        except (ImportError, frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError) as e:
            frappe.logger("huf").warning(
                f"Error loading MCP tools for agent: {e!s}"
            )

    # Load native tools from Agent Tool Function documents
    allowed_tool_docs = PermissionAwareToolRegistry.get_allowed_tools(
        agent, frappe.session.user, model_name=model_name
    )

    desktop_attached_docs = []
    for function_doc in allowed_tool_docs:
        try:
            if _is_desktop_tool_doc(function_doc):
                # Never built by the generic path: exposure is decided once,
                # below, against the run's live desktop_ctx.
                desktop_attached_docs.append(function_doc)
                continue

            if lazy_enabled:
                tool_name = function_doc.tool_name or ""
                is_always_eager = (
                    tool_name in _LAZY_DISCOVERY_ALWAYS_EAGER_TOOL_NAMES
                    or "memory" in tool_name.lower()
                )
                if not is_always_eager and tool_name not in discovered_tool_names:
                    # Deferred: skip building this tool entirely (don't even
                    # fetch its schema) until the model discovers it.
                    continue

            # Resolution moved to huf.ai.tool_invocation (T-10): one
            # type->function_path map shared with the deterministic tool
            # path, instead of a hand-duplicated if/elif chain. Behavior is
            # identical to the chain this replaced -- Custom
            # Function/App Provided and Client Side Tool still short-circuit
            # with their own continue guard before the static-map lookup.
            _tool_doc_dict = {
                "types": function_doc.types,
                "function_path": function_doc.function_path,
                "function_name": function_doc.function_name,
            }
            if function_doc.types in DYNAMIC_FUNCTION_PATH_TYPES:
                if not function_doc.function_path:
                    continue
                function_path = function_doc.function_path
            elif function_doc.types == CLIENT_SIDE_TOOL_TYPE:
                function_path = CLIENT_SIDE_TOOL_FUNCTION_PATH
                if not function_doc.function_name:
                    continue
            else:
                function_path = TYPE_TO_FUNCTION_PATH.get(function_doc.types)
                if not function_path:
                    continue

            if function_doc:
                params = {}
                if function_doc.params:
                    try:
                        params = json.loads(function_doc.params)
                    except json.JSONDecodeError as e:
                        frappe.logger("huf").debug(
                            f"Error parsing params for {function_doc.name}: {e!s}"
                        )

                if "additionalProperties" in params:
                    del params["additionalProperties"]

                # extra_args derivation moved to
                # huf.ai.tool_invocation.build_extra_args (T-10) -- same
                # branches, same values. GET/POST's tool_name is deliberately
                # NOT taken from there: this file injects it via the
                # dedicated `_function.__name__ in [...]` check below
                # (unconditional overwrite, using the friendly `name`), which
                # predates this refactor and is left untouched.
                _tool_doc_dict["reference_doctype"] = function_doc.reference_doctype
                _tool_doc_dict["agent"] = function_doc.agent
                extra_args = build_extra_args(_tool_doc_dict)
                extra_args.pop("tool_name", None)

                # Client Side Tool calls block (waiting on the browser to report a
                # result via submit_client_tool_result); run them off the event loop.
                # ``blocking`` defaults to checked, so a missing/unset field (e.g. on
                # rows created before this field existed) still behaves as blocking.
                is_blocking = (
                    bool(getattr(function_doc, "blocking", 1))
                    if function_doc.types == "Client Side Tool"
                    else False
                )

                tool = create_function_tool(
                    function_doc.tool_name,
                    function_doc.description,
                    function_path,
                    params,
                    extra_args=extra_args,
                    tool_type=function_doc.types,
                    allowed_for_guest=bool(function_doc.allowed_for_guest),
                    blocking=is_blocking,
                )

                if tool:
                    tools.append(tool)

        except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, AttributeError) as e:
            frappe.logger("huf").debug(
                f"Error processing function {function_doc.name}: {e!s}"
            )

    if desktop_attached_docs:
        tools.extend(_build_desktop_tools(desktop_attached_docs, desktop_ctx, agent=agent))

    if lazy_enabled:
        # The discovery tools themselves are not something an agent author is
        # expected to attach via agent_tool - without them the model could
        # never unlock anything else, so build them unconditionally (same
        # pattern as the memory tools below): looked up by tool_name from the
        # Agent Tool Function records synced from LAZY_DISCOVERY_TOOLS
        # (huf.ai.tools._registry), not gated on the agent's tool list.
        existing_tool_names = {getattr(t, "name", "") for t in tools}
        for tool_name in _LAZY_DISCOVERY_TOOL_NAMES:
            if tool_name in existing_tool_names:
                continue
            function_name = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
            if not function_name:
                continue
            try:
                function_doc = frappe.get_doc("Agent Tool Function", function_name)
                params = {}
                if function_doc.params:
                    params = json.loads(function_doc.params)
                tool = create_function_tool(
                    function_doc.tool_name,
                    function_doc.description,
                    function_doc.function_path,
                    params,
                    tool_type=function_doc.types,
                )
                if tool:
                    tools.append(tool)
                    existing_tool_names.add(tool_name)
            except Exception as e:
                frappe.logger("huf").debug(f"Error wiring lazy discovery tool {tool_name}: {e!s}")

    # Load tools from attached skills (mandatory and optional)
    try:
        from huf.ai.skills.loader import load_all_skill_tools
        skill_tools = load_all_skill_tools(agent, frappe.session.user)
        if skill_tools:
            # Skill-attached tools must not bypass the desktop ctx gate.
            from huf.ai.tools._registry import DESKTOP_DYNAMIC_TOOL_PREFIXES, DESKTOP_TOOL_NAMES
            tools.extend(
                t for t in skill_tools
                if getattr(t, "name", "") not in DESKTOP_TOOL_NAMES
                and not str(getattr(t, "name", "")).startswith(DESKTOP_DYNAMIC_TOOL_PREFIXES)
            )
    except Exception as e:
        frappe.log_error(
            title="Skill Tool Loading Error",
            message=f"Error loading skill tools for agent: {e!s}",
        )

    if hasattr(agent, "enable_conversation_data") and agent.enable_conversation_data:
        existing_types = [t.name for t in tools]

        # Get Conversation Data
        if "get_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="get_conversation_data",
                description="Retrieve a specific value from the conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_get_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the item to retrieve"},
                        "default": {"type": "string", "description": "Default value if not found"}
                    },
                    "required": ["name"]
                }
            )
            if tool:
                tools.append(tool)

        # Set Conversation Data
        if "set_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="set_conversation_data",
                description="Store a value in the conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_set_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the item to set"},
                        "value": {"type": "string", "description": "Value to store (scalar, object, or array)"},
                        "value_type": {"type": "string", "description": "Type of value (scalar, object, array). Optional."},
                        "source": {"type": "string", "description": "Source of data (agent/user). Default: agent"},
                        "auto_inject": {"type": "boolean", "description": "Whether to auto-inject this variable in the system prompt on future turns. Set false for high-volume variables to prevent context bloat. Default: true"},
                        "inject_mode": {"type": "string", "enum": ["visible", "hidden"], "description": "Injection mode. 'visible' to auto-inject in system prompt (if enabled on agent), 'hidden' to keep it in the data layer only. Default: visible"}
                    },
                    "required": ["name", "value"]
                }
            )
            if tool:
                tools.append(tool)

        # Load Conversation Data
        if "load_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="load_conversation_data",
                description="Load the entire conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_load_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            )
            if tool:
                tools.append(tool)

    if getattr(agent, "enable_memory", False):
        existing_tool_names = {getattr(t, "name", "") for t in tools}
        memory_tool_specs = []
        if getattr(agent, "enable_memory_search_tool", True):
            memory_tool_specs.append(("search_memory_records", "Search Memory Records"))
        if getattr(agent, "enable_memory_write_tool", True):
            memory_tool_specs.append(("save_memory_record", "Save Memory Record"))

        for tool_name, tool_type in memory_tool_specs:
            if tool_name in existing_tool_names:
                continue
            function_name = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
            if not function_name:
                continue
            try:
                function_doc = frappe.get_doc("Agent Tool Function", function_name)
                params = {}
                if function_doc.params:
                    params = json.loads(function_doc.params)
                tool = create_function_tool(
                    function_doc.tool_name,
                    function_doc.description,
                    function_doc.function_path,
                    params,
                    tool_type=tool_type,
                )
                if tool:
                    tools.append(tool)
                    existing_tool_names.add(tool_name)
            except Exception as e:
                frappe.logger("huf").debug(f"Error wiring memory tool {tool_name}: {e!s}")

    # Bound Agent Procedures (T-31): exposed as tool-like capabilities computed at
    # request time from enabled Agent Procedure Binding rows, never as an Agent Tool
    # Function row per (agent, procedure) pair. See huf.ai.graph.procedure_binding for
    # the read-only re-check (I8) and the hard per-agent cap this applies.
    try:
        from huf.ai.graph.procedure_binding import build_procedure_binding_tools
        existing_tool_names = {getattr(t, "name", "") for t in tools}
        for tool in build_procedure_binding_tools(agent, **kwargs):
            tool_name = getattr(tool, "name", "")
            # T-34: when lazy discovery is on, a bound procedure's schema only enters
            # context once the model has unlocked it via load_tools (same
            # discovered_tool_names / "_lazy_tools" mechanism as ordinary tools above).
            # When lazy discovery is off this branch never runs and behaviour is
            # byte-for-byte the T-31 eager path.
            if lazy_enabled and tool_name not in discovered_tool_names:
                continue
            if tool_name not in existing_tool_names:
                tools.append(tool)
                existing_tool_names.add(tool_name)
    except Exception as e:
        frappe.logger("huf").debug(f"Error building bound-procedure tools for agent: {e!s}")

    existing_types = [t.name for t in tools] if tools else []
    if "get_result_context" not in existing_types:
        tool = create_function_tool(
            name="get_result_context",
            description="Get the full result context of an out-of-band message reference by its handle.",
            tool_name="huf.ai.sdk_tools.handle_get_result_context",
            parameters={
                "type": "object",
                "properties": {
                    "reference_doctype": {
                        "type": "string",
                        "description": "The DocType of the referenced record (e.g. 'Agent Tool Call')"
                    },
                    "reference_name": {
                        "type": "string",
                        "description": "The name/ID of the referenced record"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "For Agent Context Artifact: line offset to start reading the "
                        "payload from (0-based). Ignored for other reference types."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For Agent Context Artifact: maximum number of lines of the "
                        "payload to return. Ignored for other reference types."
                    }
                },
                "required": ["reference_doctype", "reference_name"]
            }
        )
        if tool:
            tools.append(tool)

    return tools


def create_function_tool(
    name: str,
    description: str,
    tool_name: str,
    parameters: dict[str, Any],
    extra_args: dict[str, Any] = None,
    tool_type: str = None,
    allowed_for_guest: bool = False,
    blocking: bool = False,
    pin_run_context: bool = False,
) -> FunctionTool:
    """
    Create a FunctionTool for Huf Tool functions

    Args:
        name: Tool name
        description: Tool description
        function_name: Function name to call
        parameters: Function parameters schema
        extra_args: Extra arguments to pass to the function
        blocking: When True, the tool function is invoked via
            ``asyncio.to_thread`` instead of being awaited inline. Tool
            functions that perform a bounded blocking wait (e.g. the
            client-side tool round trip) would otherwise stall the event
            loop for the whole run; running them on a worker thread lets
            other concurrent work keep going while this call waits. If the
            function exposes ``prepare`` / ``execute`` attributes (Desktop
            Workspace handlers), ``prepare`` runs on the loop thread (it may read
            the database) and only ``execute`` runs in the worker thread, so the
            shared DB connection is never used from two threads.
        pin_run_context: When True, ``agent_run_id`` / ``conversation_id`` /
            ``call_id`` are taken from the server-side run context and the SDK
            tool_call_id and OVERWRITE anything the model passed.

    Returns:
        FunctionTool: Function tool
    """

    function = get_function_from_name(tool_name, tool_type=tool_type)

    if not function:
        return None

    try:
        _extra_args = extra_args or {}
        _function = function

        async def on_invoke_tool(ctx=None, args_json: str = None) -> str:

            # Permission check before execution
            if tool_type:
                perm_check = _check_tool_permission(tool_type, allowed_for_guest=allowed_for_guest)
                if not perm_check["allowed"]:
                    return json.dumps({"error": perm_check["error"], "denied": True})

            try:
                if args_json is None and isinstance(ctx, str):
                    args_json = ctx
                    ctx = None

                args_dict = json.loads(args_json or "{}")

                _merge_run_context(args_dict, ctx)
                if pin_run_context:
                    # N7: one nonce per SDK invocation, so a provider reusing a tool_call_id
                    # in a later invocation never reads this one's cached result.
                    from huf.ai.desktop_executor import mint_invocation_nonce

                    _pin_run_identity(args_dict, ctx, mint_invocation_nonce())

                if _extra_args:
                    args_dict.update(_extra_args)

                if pin_run_context:
                    # N8: only this path can mint the token the Desktop handlers require, so
                    # flows / procedures / direct API calls cannot reach them.
                    from huf.ai.tools.desktop_workspace import issue_pin_token

                    args_dict["_dx_pin"] = issue_pin_token(
                        args_dict.get("agent_run_id"),
                        args_dict.get("_dx_executor_id"),
                        args_dict.get("_dx_user"),
                    )

                if "ignore_permissions" in args_dict:
                    del args_dict["ignore_permissions"]

                if allowed_for_guest and frappe.session.user == "Guest":
                    if tool_type in _GUEST_DOCTYPE_PINNED_TYPES and not _extra_args.get("reference_doctype"):
                        return json.dumps({
                            "error": (
                                "This tool is not available for guest access: it has no "
                                "fixed target doctype configured."
                            ),
                            "denied": True,
                        })
                    if tool_type in _GUEST_REPORT_PINNED_TYPES and not _extra_args.get("reference_report"):
                        return json.dumps({
                            "error": (
                                "This tool is not available for guest access: it has no "
                                "fixed target report configured."
                            ),
                            "denied": True,
                        })
                    args_dict["ignore_permissions"] = True

                    # Override report_name with reference_report if pinned for guest.
                    # Scoped to this branch only -- a non-guest caller's LLM-supplied
                    # report_name must not be silently overwritten by a guest pin.
                    if _extra_args.get("reference_report"):
                        args_dict["report_name"] = _extra_args["reference_report"]

                if _function.__name__ in ["handle_get_request", "handle_post_request"]:
                    args_dict["tool_name"] = name

                sig = inspect.signature(_function)
                accepts_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if accepts_kwargs:
                    call_kwargs = args_dict
                else:
                    valid_params = set(sig.parameters.keys())

                    call_kwargs = {
                        k: v for k, v in args_dict.items()
                        if k in valid_params
                    }

                if blocking:
                    # Run off the event loop: a blocking tool function (e.g. one
                    # that polls for a browser-reported result for up to tens of
                    # seconds) would otherwise stall this whole run. Mirrors the
                    # asyncio.to_thread precedent in huf.ai.handlers.media (TTS
                    # via litellm.speech).
                    prepare = getattr(_function, "prepare", None)
                    execute = getattr(_function, "execute", None)
                    if callable(prepare) and callable(execute):
                        # DB work (validation, run lookup) here on the loop thread;
                        # only the Redis wait goes to a worker thread.
                        prepared = prepare(**call_kwargs)
                        result = await asyncio.to_thread(execute, prepared)
                    else:
                        result = await asyncio.to_thread(_function, **call_kwargs)
                else:
                    result = _function(**call_kwargs)

                # Handle async functions
                if asyncio.iscoroutine(result):
                    result = await result

                if hasattr(result, "as_dict") and callable(getattr(result, "as_dict", None)):
                    result = result.as_dict()

                return json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)

            except Exception as e:
                frappe.logger("huf").debug(
                    f"Error in on_invoke_tool for tool '{name}': {e!s}\n{frappe.get_traceback()}"
                )
                return json.dumps({"error": str(e)})

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', (name or ""))
        if len(safe_name) > 128:
            safe_name = safe_name[:128]

        if safe_name != name:
            frappe.log("SDK Functions Debug", f"Tool runtime name '{safe_name}' created for friendly name '{name}'")

        # Tools with no declared parameters arrive as an empty/typeless schema, which
        # OpenAI rejects for the whole request ('type: "None"'); normalise to an
        # empty object schema.
        if not isinstance(parameters, dict) or not parameters.get("type"):
            parameters = {"type": "object", "properties": {}, **(parameters or {})}
            parameters["type"] = "object"

        tool = FunctionTool(
            name=safe_name,
            description=description,
            params_json_schema=parameters,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=False
        )

        return tool

    except (TypeError, ValueError, AttributeError) as e:
        frappe.logger("huf").debug(
            f"Error creating FunctionTool for {name}: {e!s}\n{frappe.get_traceback()}"
        )
        return None


def get_function_from_name(tool_name: str, tool_type: str | None = None) -> Callable:
    """
    Get a function from its name

    Args:
        tool_name: Fully qualified function name (module.function)
        tool_type: Optional tool type ("App Provided", "Custom Function", etc.)
                   When "App Provided", validates against the hook allow-set.

    Returns:
        Callable: Function, or None if not found or validation fails
    """

    if tool_type == "App Provided":
        from huf.ai.tool_registry import get_hook_declared_function_paths
        if tool_name not in get_hook_declared_function_paths():
            frappe.logger("huf").debug(
                f"App Provided function path not in hook allow-set: {tool_name}"
            )
            return None

    try:
        try:
            module_name, func_name = tool_name.rsplit(".", 1)
        except ValueError:
            frappe.logger("huf").debug(
                f"Invalid function name format: {tool_name}. Should be 'module.function'"
            )
            return None

        try:
            module = __import__(module_name, fromlist=[func_name])
        except ImportError as ie:
            frappe.logger("huf").debug(f"Module import error: {ie!s}")
            return None

        try:
            available_attrs = dir(module)
        except (TypeError, AttributeError) as e:
            frappe.logger("huf").debug(f"Error getting module attributes: {e!s}")

        try:
            function = getattr(module, func_name)
        except AttributeError as ae:
            frappe.logger("huf").debug(f"Function not found in module: {ae!s}")
            return None

        if not callable(function):
            return None

        return function

    except (ImportError, AttributeError, TypeError, ValueError) as e:
        frappe.logger("huf").debug(
            f"Unexpected error getting function {tool_name}: {e!s}\n{frappe.get_traceback()}"
        )
        return None


ALLOWED_RESULT_CONTEXT_DOCTYPES = frozenset({
    "Agent Tool Call",
    "Agent Context Artifact",
})


def handle_get_result_context(
    reference_doctype: str,
    reference_name: str,
    offset: int = None,
    limit: int = None,
    **kwargs,
):
    """
    Get the full result context of an out-of-band message reference by its handle.

    Only explicitly allow-listed DocTypes are exposed, and the caller must have
    Frappe read permission on the requested document. Permission is re-checked
    here against the *reader* on every call (I1, I2) -- a handle stored in an
    earlier message is never itself authority, only a pointer.

    ``offset``/``limit`` (line-based) bound how much of an ``Agent Context
    Artifact``'s payload is read back in a single call -- see
    ``huf.ai.context_artifacts.read_context_artifact_payload``. They are
    ignored for ``Agent Tool Call``.
    """
    try:
        if not reference_doctype or not reference_name:
            return {"success": False, "error": "Both reference_doctype and reference_name are required."}

        if reference_doctype not in ALLOWED_RESULT_CONTEXT_DOCTYPES:
            # Security event: retain Error Log for unauthorized allow-list attempts.
            frappe.log_error(
                title="Security: get_result_context allow-list",
                message=f"get_result_context rejected for {reference_doctype}",
            )
            return {"success": False, "error": f"DocType '{reference_doctype}' is not accessible via get_result_context."}

        if not frappe.db.exists(reference_doctype, reference_name):
            return {"success": False, "error": f"Document {reference_name} of type {reference_doctype} not found."}

        doc = frappe.get_doc(reference_doctype, reference_name)

        if not frappe.has_permission(reference_doctype, "read", doc=doc):
            return {"success": False, "error": f"You do not have permission to read {reference_doctype} {reference_name}."}

        # If it's Agent Tool Call, retrieve the tool_result
        if reference_doctype == "Agent Tool Call":
            return {
                "success": True,
                "tool": doc.tool,
                "tool_args": doc.tool_args,
                "status": doc.status,
                "tool_result": doc.tool_result,
                "error_message": doc.error_message
            }

        # If it's Agent Context Artifact, retrieve payload. Fix for F-12: every
        # artifact that exists in production is artifact_type="File" with an
        # empty payload_json, so returning payload_json alone (the old
        # behaviour) returned nothing -- drill-down had never worked end to
        # end. read_context_artifact_payload reads payload_file when present,
        # bounded by offset/limit so a large artifact still can't re-enter
        # context unbounded (I7).
        if reference_doctype == "Agent Context Artifact":
            from huf.ai.context_artifacts import read_context_artifact_payload

            payload = read_context_artifact_payload(doc, offset=offset, limit=limit)
            return {
                "success": True,
                "artifact_type": doc.artifact_type,
                "summary": doc.summary,
                "payload_file": doc.payload_file,
                "payload": payload,
                "reference_doctype": doc.reference_doctype,
                "reference_name": doc.reference_name
            }

        # Unreachable because of the allow-list, but kept as defense-in-depth.
        return {"success": False, "error": "Unexpected DocType."}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_get_result_context failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}



