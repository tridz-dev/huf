"""Runtime skill loader for the Huf Skills system.

This module turns Skill definitions attached to an Agent into concrete runtime
capabilities: FunctionTool instances, mandatory knowledge source configs,
MCP server names, and system prompt additions.

``create_list_skills_tool`` / ``handle_list_skills`` (T4.03, PLAN.md §3.6 "Skill
Selection", IP §10.4) additionally apply the Agent's ``Skill Selection`` decision
binding, if any, as a **two-request** pattern:

- **Request 1 -- wide rank + gate**: one ``decide_for_surface`` call over every skill
  permitted on the agent, using truncated (~54 char) descriptions, asking for a top-N
  shortlist plus a gate signal (IP §10.4 "Request 1"). This is the only call made for
  Off/Shadow/error (falls straight back to the unmodified full list) and for Advise
  (the shortlist/gate answer becomes the hint appended to the full list; nothing is
  narrowed -- D18).
- **Request 2 -- shortlist rerank** (Enforce only, and only when Request 1's shortlist
  has more than one candidate): a second, independent ``service.run_policy`` call
  against the *same* resolved policy, now over only the shortlisted skills with full
  descriptions and the opening section of each skill's instructions (IP §10.4
  "Request 2"). ``decide_for_surface`` has no parameter for a caller-supplied latency
  override, so Request 2 is made via ``service.run_policy`` directly (documented
  choice per the T4.03 brief) with an explicit ``latency_budget_ms`` computed as the
  binding's configured budget minus Request 1's measured elapsed time -- the two
  requests together respect one Skill Selection budget rather than doubling it.

``list_skills`` remains available unnarrowed whenever the decision layer is Off,
disabled, erroring, or produces nothing usable -- it is always the escape hatch.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import frappe
from agents import FunctionTool


# Map of standard tool types to their handler function paths.
# Mirrors the mapping in huf.ai.sdk_tools.create_agent_tools.
_STANDARD_TOOL_PATHS = {
    "Get List": "huf.ai.sdk_tools.handle_get_list",
    "Get Document": "huf.ai.sdk_tools.handle_get_document",
    "Update Document": "huf.ai.sdk_tools.handle_update_document",
    "Create Document": "huf.ai.sdk_tools.handle_create_document",
    "Delete Document": "huf.ai.sdk_tools.handle_delete_document",
    "Get Multiple Documents": "huf.ai.sdk_tools.handle_get_documents",
    "Create Multiple Documents": "huf.ai.sdk_tools.handle_create_documents",
    "Update Multiple Documents": "huf.ai.sdk_tools.handle_update_documents",
    "Delete Multiple Documents": "huf.ai.sdk_tools.handle_delete_documents",
    "Submit Document": "huf.ai.sdk_tools.handle_submit_document",
    "Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
    "Get Value": "huf.ai.sdk_tools.handle_get_value",
    "Set Value": "huf.ai.sdk_tools.handle_set_value",
    "Get Report Result": "huf.ai.sdk_tools.handle_get_report_result",
    "GET": "huf.ai.http_handler.handle_get_request",
    "POST": "huf.ai.http_handler.handle_post_request",
    "Run Agent": "huf.ai.sdk_tools.handle_run_agent",
    "Attach File to Document": "huf.ai.sdk_tools.handle_attach_file_to_document",
    "Get Conversation Data": "huf.ai.sdk_tools.handle_get_conversation_data",
    "Set Conversation Data": "huf.ai.sdk_tools.handle_set_conversation_data",
    "Load Conversation Data": "huf.ai.sdk_tools.handle_load_conversation_data",
}


def _skill_doctypes_exist() -> bool:
    """Return True if the Skill DocTypes have been installed."""
    try:
        return frappe.db.exists("DocType", "Skill") and frappe.db.exists("DocType", "Agent Skill")
    except Exception:
        return False


def get_agent_skills(agent_name: str, mode: Optional[str] = None):
    """Return Skill docs attached to an agent, optionally filtered by mode.

    Only skills with status "Active" are returned.
    """
    if not _skill_doctypes_exist():
        return []

    try:
        agent = frappe.get_doc("Agent", agent_name)
    except Exception:
        return []

    skills = []
    for row in agent.get("agent_skill", []):
        if mode and getattr(row, "mode", None) != mode:
            continue
        try:
            skill = frappe.get_doc("Skill", row.skill)
            if getattr(skill, "status", "Active") != "Active":
                continue
            skills.append(skill)
        except Exception:
            continue

    return skills


def get_agent_skill_mcp_servers(agent_name: str) -> list[str]:
    """Return enabled MCP server names from all attached skills."""
    servers = []
    seen = set()

    for skill in get_agent_skills(agent_name):
        for row in skill.get("skill_mcp_servers", []):
            if not getattr(row, "enabled", 1):
                continue
            name = getattr(row, "mcp_server", None)
            if name and name not in seen:
                seen.add(name)
                servers.append(name)

    return servers


def _resolve_tool_function_path(tool_doc) -> Optional[str]:
    """Resolve the handler function path for an Agent Tool Function doc."""
    tool_type = tool_doc.types

    if tool_type in ("Custom Function", "App Provided"):
        return tool_doc.function_path or None

    if tool_type == "Client Side Tool":
        if not tool_doc.function_name:
            return None
        return "huf.ai.client_side_tool.client_side_function"

    return _STANDARD_TOOL_PATHS.get(tool_type)


def _build_tool_parameters(tool_doc) -> dict:
    """Build the parameter schema for a tool from its doc."""
    params = {}

    # Prefer the computed function definition, fall back to raw params JSON.
    raw = getattr(tool_doc, "function_definition", None) or getattr(tool_doc, "params", None)
    if raw:
        try:
            params = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            params = {}

    if not isinstance(params, dict):
        params = {}

    if "additionalProperties" in params:
        del params["additionalProperties"]

    return params


def _build_extra_args(tool_doc, skill_tool_row=None) -> dict:
    """Build extra arguments passed to the tool handler at runtime."""
    extra_args = {}
    tool_type = tool_doc.types

    if tool_type == "Attach File to Document" and tool_doc.reference_doctype:
        extra_args["reference_doctype"] = tool_doc.reference_doctype

    elif (
        tool_type
        in {
            "Get Document",
            "Get Multiple Documents",
            "Get List",
            "Create Document",
            "Create Multiple Documents",
            "Update Document",
            "Update Multiple Documents",
            "Delete Document",
            "Delete Multiple Documents",
        }
        and tool_doc.reference_doctype
    ):
        extra_args["reference_doctype"] = tool_doc.reference_doctype

    elif tool_type == "Client Side Tool" and tool_doc.function_name:
        extra_args["function_name"] = tool_doc.function_name

    elif tool_type == "Run Agent" and tool_doc.agent:
        extra_args["target_agent_name"] = tool_doc.agent

    return extra_args


def load_all_skill_tools(agent_doc, user: str) -> list[FunctionTool]:
    """Return FunctionTool instances from all tools declared by attached skills.

    Both Mandatory and Optional skills are loaded at agent construction time.
    Tools are filtered by the user's permissions.
    """
    tools: list[FunctionTool] = []

    # Lazy imports to avoid circular dependencies between sdk_tools and loader.
    from huf.ai.sdk_tools import create_function_tool
    from huf.ai.tool_registry import PermissionAwareToolRegistry

    if not _skill_doctypes_exist():
        return tools

    agent_name = getattr(agent_doc, "agent_name", None)
    if not agent_name:
        return tools

    seen_names: set[str] = set()

    for skill in get_agent_skills(agent_name):
        for skill_tool in skill.get("skill_tools", []):
            try:
                tool_doc = frappe.get_doc("Agent Tool Function", skill_tool.tool)
            except Exception:
                continue

            if not PermissionAwareToolRegistry._can_use_tool(tool_doc, user):
                continue

            function_path = _resolve_tool_function_path(tool_doc)
            if not function_path:
                continue

            name = tool_doc.tool_name
            if not name or name in seen_names:
                continue

            description = getattr(skill_tool, "description", None) or tool_doc.description or ""
            params = _build_tool_parameters(tool_doc)
            extra_args = _build_extra_args(tool_doc, skill_tool)

            try:
                tool = create_function_tool(
                    name=name,
                    description=description,
                    tool_name=function_path,
                    parameters=params,
                    extra_args=extra_args,
                    tool_type=tool_doc.types,
                    allowed_for_guest=bool(getattr(tool_doc, "allowed_for_guest", False)),
                )
            except Exception as e:
                frappe.log_error(
                    title="Skill Tool Loading Error",
                    message=f"Error creating skill tool '{name}' from skill '{skill.name}': {e!s}",
                )
                continue

            if tool:
                tools.append(tool)
                seen_names.add(name)

    return tools


def get_mandatory_skill_knowledge(agent_name: str) -> list[dict[str, Any]]:
    """Return mandatory knowledge source configs from attached skills.

    The returned dicts are compatible with huf.ai.knowledge.context_builder.build_knowledge_context.
    """
    sources = []
    seen: set[str] = set()

    for skill in get_agent_skills(agent_name):
        for row in skill.get("skill_knowledge", []):
            if getattr(row, "mode", "Mandatory") != "Mandatory":
                continue

            source_name = getattr(row, "knowledge_source", None)
            if not source_name or source_name in seen:
                continue

            seen.add(source_name)
            sources.append({
                "knowledge_source": source_name,
                "priority": getattr(row, "priority", 0) or 0,
                "max_chunks": getattr(row, "max_chunks", 5) or 5,
                "token_budget": getattr(row, "token_budget", 2000) or 2000,
            })

    # Sort by priority (higher first) to align with agent-level knowledge handling.
    sources.sort(key=lambda x: x["priority"], reverse=True)
    return sources


def get_skill_instructions(agent_name: str) -> str:
    """Concatenate instructions from all attached skills."""
    parts = []

    for skill in get_agent_skills(agent_name):
        instructions = getattr(skill, "instructions", None)
        if instructions and instructions.strip():
            parts.append(instructions.strip())

    if not parts:
        return ""

    return "\n\n".join(parts)


def get_skill_prompts(agent_name: str) -> list[dict[str, str]]:
    """Return prompt bodies from attached skills, tagged by usage.

    Only active Agent Prompt documents are included. Each entry contains:
    - ``usage``: "System" or "User"
    - ``body``: the prompt template body
    - ``skill``: the skill_name the prompt came from
    """
    prompts: list[dict[str, str]] = []

    if not frappe.db.exists("DocType", "Agent Prompt"):
        return prompts

    for skill in get_agent_skills(agent_name):
        for row in skill.get("skill_prompts", []):
            try:
                prompt_doc = frappe.get_doc("Agent Prompt", row.prompt)
                if not getattr(prompt_doc, "is_active", 1):
                    continue
                prompts.append(
                    {
                        "usage": row.usage or "System",
                        "body": prompt_doc.prompt_body or "",
                        "skill": skill.skill_name,
                    }
                )
            except Exception:
                continue

    return prompts


def get_optional_skills_preamble(agent_name: str) -> str:
    """Return a system prompt section listing optional skills."""
    optional_skills = []

    for skill in get_agent_skills(agent_name, mode="Optional"):
        description = getattr(skill, "description", None) or ""
        optional_skills.append(f"- {skill.skill_name}: {description}".strip())

    if not optional_skills:
        return ""

    return (
        "\n\nOptional skills available. "
        "Only use an optional skill when the user's request clearly matches its description:\n"
        + "\n".join(optional_skills)
    )


SKILL_SELECTION_SURFACE = "Skill Selection"

# IP §10.4 "Request 1": truncation length used in the reference (TypeSafe) implementation.
_WIDE_DESCRIPTION_CHARS = 54
# IP §10.4 "Request 1": shortlist size ("top 3").
_SHORTLIST_TOP_N = 3
# IP §10.4 "Request 2": how much of a skill's own instructions counts as its "opening section".
_SHORTLIST_INSTRUCTIONS_PREVIEW_CHARS = 400
# PLAN.md §3.6 "Latency (D6)": per-surface default enforce budget for tool/skill/procedure
# selection, used when the binding has no `latency_budget_ms` override.
_DEFAULT_LATENCY_BUDGET_MS = 1500


def _skill_selection_origin(agent_name: str, conversation_id: Optional[str], agent_run_id: Optional[str]):
    from huf.ai.decision.types import DecisionOrigin

    try:
        owner_user = frappe.session.user
    except Exception:
        # frappe.session is a request-bound LocalProxy: outside a bound request/site
        # context (e.g. unit tests) accessing it raises RuntimeError, not AttributeError,
        # so a plain getattr(..., default) does not catch it.
        owner_user = None

    return DecisionOrigin(
        origin_type="Agent Run",
        agent=agent_name,
        agent_run=agent_run_id,
        conversation=conversation_id,
        owner_user=owner_user,
    )


def _latest_user_message_text(conversation_id: str, limit_chars: int = 2000) -> str:
    """Best-effort last user turn, for the gate/rank questions to judge relevance against.

    Never raises: an unavailable/mistyped conversation just means the decision runs with
    less context, not that skill discovery breaks.
    """
    try:
        content = frappe.db.get_value(
            "Agent Message",
            {"conversation": conversation_id, "role": "user"},
            "content",
            order_by="conversation_index desc",
        )
    except Exception:
        return ""

    if not content:
        return ""
    return content[:limit_chars]


def _skill_selection_state(agent_name: str, conversation_id: Optional[str]) -> dict:
    state = {"agent_name": agent_name}
    if conversation_id:
        state["conversation_id"] = conversation_id
        task_text = _latest_user_message_text(conversation_id)
        if task_text:
            state["task"] = task_text
    return state


def _wide_skill_option(skill):
    from huf.ai.decision.types import Option

    description = (getattr(skill, "description", None) or "").strip()
    if len(description) > _WIDE_DESCRIPTION_CHARS:
        description = description[:_WIDE_DESCRIPTION_CHARS].rstrip()
    return Option(id=skill.skill_name, description=description)


def _shortlist_skill_option(skill):
    from huf.ai.decision.types import Option

    description = (getattr(skill, "description", None) or "").strip()
    instructions = (getattr(skill, "instructions", None) or "").strip()
    preview = instructions[:_SHORTLIST_INSTRUCTIONS_PREVIEW_CHARS]
    body = f"{description}\n{preview}" if description and preview else (description or preview)
    return Option(id=skill.skill_name, description=body)


def _narrow_response_to_ids(response, permitted_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Turn a successful ``DecisionResponse`` into an ordered subset of ``permitted_ids``.

    Deliberately mirrors (but does not import, since it is a private helper)
    ``huf.ai.decision.agent_surfaces._narrow_to_subset``'s ordering rule: probability-
    scored answers first, plain ``select`` value treated as its own confidence (or 1.0),
    ties/unscored ids fall back to candidate order, ids outside ``permitted_ids`` are
    dropped rather than passed through (I-DR1).
    """
    permitted_set = set(permitted_ids)
    rank_of = {candidate_id: index for index, candidate_id in enumerate(permitted_ids)}
    scored: dict[str, float] = {}

    for answer in response.answers.values():
        probabilities = getattr(answer, "probabilities", None)
        if probabilities:
            for candidate_id, score in probabilities.items():
                if candidate_id in permitted_set and candidate_id not in scored and isinstance(score, (int, float)):
                    scored[candidate_id] = float(score)
        else:
            value = getattr(answer, "value", None)
            if isinstance(value, str) and value in permitted_set and value not in scored:
                confidence = getattr(answer, "confidence", None)
                scored[value] = confidence if confidence is not None else 1.0

    if not scored:
        return ()

    ordered = sorted(scored, key=lambda candidate_id: (-scored[candidate_id], rank_of[candidate_id]))
    return tuple(ordered)


def _configured_latency_budget_ms(agent_doc, resolved) -> int:
    for binding in getattr(agent_doc, "decision_bindings", None) or ():
        if (
            getattr(binding, "surface", None) == resolved.surface
            and getattr(binding, "policy", None) == resolved.policy
            and getattr(binding, "mode", None) == resolved.mode
        ):
            override = getattr(binding, "latency_budget_ms", None)
            if override:
                return int(override)
            break
    return _DEFAULT_LATENCY_BUDGET_MS


def _decide_skill_selection(agent_doc, skills, *, conversation_id=None, agent_run_id=None):
    """Run the Skill Selection two-request pattern (IP §10.4) for ``skills``.

    Returns ``None`` when there is nothing to do differently (Off, Shadow, disabled, any
    error/timeout, or a decision that produced nothing usable) -- callers keep the full,
    unmodified skill list, exactly as before T4.03. Otherwise returns a
    ``SurfaceDecision``: ``mode="Advise"`` with ``hint`` set (candidates unchanged,
    IP §10.4 request 1 only), or ``mode="Enforce"`` with ``selected_ids`` set (an ordered,
    non-empty subset of the input skills' ids -- IP §10.4 request 1, and request 2 when
    the shortlist has more than one candidate).
    """
    from huf.ai.decision import service
    from huf.ai.decision.agent_surfaces import SurfaceDecision, decide_for_surface
    from huf.ai.decision.binding import resolve_agent_decision_binding
    from huf.ai.decision.types import CandidateSource, DecisionStatus

    agent_name = getattr(agent_doc, "agent_name", None) or getattr(agent_doc, "name", None)
    origin = _skill_selection_origin(agent_name, conversation_id, agent_run_id)
    state = _skill_selection_state(agent_name, conversation_id)

    wide_candidates = tuple(_wide_skill_option(skill) for skill in skills)

    stage1_started = time.monotonic()
    wide_decision = decide_for_surface(
        agent_doc,
        SKILL_SELECTION_SURFACE,
        wide_candidates,
        state,
        origin,
        candidate_source=CandidateSource.PERMITTED_SKILLS,
        candidate_resolver_id="skill_loader.get_agent_skills",
        top_n=_SHORTLIST_TOP_N,
        hint_kind="skills",
    )
    stage1_elapsed_ms = (time.monotonic() - stage1_started) * 1000

    if wide_decision is None:
        return None  # Off / Shadow / disabled / error / timeout -- keep today's full list.

    if wide_decision.mode != service.MODE_ENFORCE:
        # Advise: full list is kept by the caller, hint is appended -- request 1 only.
        return wide_decision

    shortlist_ids = wide_decision.selected_ids or ()
    if len(shortlist_ids) <= 1:
        # Nothing to rerank: 0 or 1 candidate is already the final answer.
        return wide_decision

    by_id = {skill.skill_name: skill for skill in skills}
    shortlisted_skills = [by_id[skill_id] for skill_id in shortlist_ids if skill_id in by_id]
    if not shortlisted_skills:
        return wide_decision

    # Request 2 (shortlist rerank) is a second, independent service.run_policy call
    # against the same resolved policy -- decide_for_surface has no parameter to accept a
    # caller-supplied latency override, so the remaining share of the *same* configured
    # Skill Selection budget is computed here and passed straight through, rather than
    # letting a second decide_for_surface call apply the full budget again and double it.
    resolved = resolve_agent_decision_binding(agent_doc, SKILL_SELECTION_SURFACE)
    if resolved is None or resolved.mode != service.MODE_ENFORCE:
        # Binding changed/vanished between the two calls (race) -- request 1's shortlist
        # is still a valid, safe subset (I-DR1); just use it.
        return wide_decision

    total_budget_ms = _configured_latency_budget_ms(agent_doc, resolved)
    remaining_budget_ms = int(total_budget_ms - stage1_elapsed_ms)
    if remaining_budget_ms <= 0:
        return wide_decision

    shortlist_candidates = tuple(_shortlist_skill_option(skill) for skill in shortlisted_skills)

    try:
        result = service.run_policy(
            resolved.policy,
            state=state,
            candidates=shortlist_candidates,
            candidate_source=CandidateSource.PERMITTED_SKILLS,
            candidate_resolver_id="skill_loader.shortlist",
            mode=service.MODE_ENFORCE,
            surface=SKILL_SELECTION_SURFACE,
            origin=origin,
            latency_budget_ms=remaining_budget_ms,
        )
    except Exception as e:
        frappe.log_error(
            title="Skill Selection Decision Error",
            message=f"Shortlist rerank failed for agent '{agent_name}': {e!s}",
        )
        return wide_decision

    if result.status != DecisionStatus.SUCCESS or result.response is None or result.response.status != DecisionStatus.SUCCESS:
        return wide_decision

    permitted_ids = tuple(skill.skill_name for skill in shortlisted_skills)
    narrowed_ids = _narrow_response_to_ids(result.response, permitted_ids)
    if not narrowed_ids:
        return wide_decision

    return SurfaceDecision(
        mode=service.MODE_ENFORCE,
        selected_ids=narrowed_ids,
        hint=None,
        decision_call=result.decision_call or wide_decision.decision_call,
    )


def handle_list_skills(
    agent_name: str,
    skill_selection_ids: Optional[list[str]] = None,
    skill_selection_hint: Optional[str] = None,
    **kwargs,
) -> str:
    """Handler for the runtime list_skills tool.

    With no active Skill Selection decision (Off/Shadow/disabled/error), behavior is
    unchanged -- every attached skill is listed, byte-for-byte identical to before T4.03
    (golden test). Enforce mode (``skill_selection_ids`` set by
    ``create_list_skills_tool``) narrows the listing to the winning skill(s) from the
    two-request pattern (IP §10.4); Advise mode (``skill_selection_hint`` set) appends the
    labelled hint without removing anything. list_skills always stays a full, ungated
    escape hatch whenever narrowing does not apply or resolves to nothing.
    """
    all_skills = get_agent_skills(agent_name)

    selected = all_skills
    if skill_selection_ids:
        wanted = set(skill_selection_ids)
        narrowed = [skill for skill in all_skills if skill.skill_name in wanted]
        if narrowed:
            selected = narrowed
        # else: an unresolvable narrowed set (e.g. a skill detached since selection)
        # falls back to the full list rather than reporting "no skills" (escape hatch).

    skills = []
    for skill in selected:
        description = getattr(skill, "description", None) or ""
        skills.append(f"- {skill.skill_name}: {description}".strip())

    if not skills:
        return "No skills are attached to this agent."

    output = "Skills available to this agent:\n" + "\n".join(skills)
    if skill_selection_hint:
        output += "\n\n" + skill_selection_hint
    return output


def create_list_skills_tool(
    agent_name: str,
    *,
    conversation_id: Optional[str] = None,
    agent_run_id: Optional[str] = None,
) -> Optional[FunctionTool]:
    """Build a runtime list_skills tool for the given agent.

    Applies the agent's Skill Selection decision binding, if any (T4.03, IP §10.4): the
    two-request rank+gate / shortlist-rerank decision runs once here, at tool-build time,
    and its result (narrowed ids for Enforce, or a hint for Advise) is baked into the
    tool's ``extra_args`` so ``handle_list_skills`` needs no further decision calls at
    invocation time. ``conversation_id`` / ``agent_run_id`` are optional -- passing them
    lets the decision's state include the current task and its origin link to the run;
    without them the decision still runs (agent-level state only), and with no binding at
    all this is a no-op (Off, identical output).
    """
    if not _skill_doctypes_exist():
        return None

    skills = get_agent_skills(agent_name)
    if not skills:
        return None

    # Lazy import to avoid circular dependency.
    from huf.ai.sdk_tools import create_function_tool

    extra_args = {"agent_name": agent_name}

    try:
        agent_doc = frappe.get_cached_doc("Agent", agent_name)
        decision = _decide_skill_selection(
            agent_doc, skills, conversation_id=conversation_id, agent_run_id=agent_run_id
        )
    except Exception as e:
        # Never let a decision-layer failure block skill discovery -- keep the full list.
        frappe.log_error(
            title="Skill Selection Decision Error",
            message=f"Skill Selection decision failed for agent '{agent_name}': {e!s}",
        )
        decision = None

    if decision is not None:
        from huf.ai.decision import service

        if decision.mode == service.MODE_ENFORCE and decision.selected_ids:
            extra_args["skill_selection_ids"] = list(decision.selected_ids)
        elif decision.hint:
            extra_args["skill_selection_hint"] = decision.hint

    try:
        return create_function_tool(
            name="list_skills",
            description="List all skills attached to this agent.",
            tool_name="huf.ai.skills.loader.handle_list_skills",
            parameters={"type": "object", "properties": {}, "required": []},
            extra_args=extra_args,
        )
    except Exception as e:
        frappe.log_error(
            title="Skill Tool Loading Error",
            message=f"Error creating list_skills tool for agent '{agent_name}': {e!s}",
        )
        return None
