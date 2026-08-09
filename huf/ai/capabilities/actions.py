"""Action capability discovery: declared (huf_tools) + framework-discovered whitelisted actions.

This module builds "action" capability descriptors (see huf.ai.capabilities.models) for a
given installed app, from two sources:

  1. Declared actions: `Agent Tool Function` records already synced from an app's `huf_tools`
     hook entries (types == "App Provided"). These are authoritative, hand-declared tools.
  2. Discovered actions: Frappe-whitelisted functions that Frappe/HUF can find via existing,
     safe enumeration surfaces (currently: the app's own `huf_tools` hook module references).
     No general filesystem/AST scanning is performed here.
"""

import json

import frappe
from frappe import _

from huf.ai.capabilities.models import build_capability_id, make_capability_descriptor
from huf.huf.doctype.agent_tool_function.agent_tool_function import get_function_metadata

DECLARED_TOOL_TYPE = "App Provided"
TOOL_DOCTYPE = "Agent Tool Function"

DECLARED_ACTION_FIELDS = [
    "name",
    "tool_name",
    "description",
    "function_path",
    "required_permission",
    "is_read_only",
    "allowed_for_guest",
    "params",
]


def _parse_parameters_schema(params_value):
    """Parse the Agent Tool Function `params` JSON field into a parameters schema dict.

    `params` is already a JSON-Schema-shaped object (built by
    AgentToolFunction.prepare_function_params). Falls back to an empty dict when
    the value is missing or not valid JSON, so callers always get a usable value.
    """
    if not params_value:
        return {}

    if isinstance(params_value, dict):
        return params_value

    try:
        parsed = json.loads(params_value)
    except (TypeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def declared_actions_for_app(app_name):
    """Return capability descriptors for App-Provided Agent Tool Function records.

    These are tools already synced from `app_name`'s `huf_tools` hook entries via
    huf.ai.tool_registry.sync_discovered_tools (types == "App Provided").
    """
    if not app_name:
        return []

    rows = frappe.get_all(
        TOOL_DOCTYPE,
        filters={"provider_app": app_name, "types": DECLARED_TOOL_TYPE},
        fields=DECLARED_ACTION_FIELDS,
    )

    descriptors = []
    for row in rows:
        source_key = row.function_path or row.name
        descriptors.append(
            make_capability_descriptor(
                kind="action",
                source_app=app_name,
                source_type="declared",
                source_key=source_key,
                title=row.tool_name,
                description=row.description,
                function_path=row.function_path,
                parameters_schema=_parse_parameters_schema(row.params),
                required_permission=row.required_permission,
                read_only=bool(row.is_read_only),
                allow_guest=bool(row.allowed_for_guest),
                visibility="recommended",
                actionability="actionable_now",
                confidence=1.0,
            )
        )

    return descriptors


def _iter_declared_function_paths(app_name):
    """Yield distinct dotted function paths declared by `app_name`'s huf_tools hook.

    This reuses the same hook-scanning surface as huf.ai.tool_registry (the only
    safe, existing app-scoped enumeration of functions in this codebase) rather than
    walking the filesystem. It intentionally does not attempt to discover whitelisted
    functions that are not referenced by a huf_tools entry.
    """
    from huf.ai.tool_registry import _normalize_hook_tools

    seen = set()
    hook_entries = frappe.get_hooks("huf_tools", app_name=app_name) or []

    for hook_entry in hook_entries:
        for tool_def in _normalize_hook_tools(hook_entry):
            function_path = (tool_def or {}).get("function_path")
            if function_path and function_path not in seen:
                seen.add(function_path)
                yield function_path


def discover_whitelisted_actions_for_app(app_name, limit=200):
    """Best-effort discovery of Frappe-whitelisted functions for `app_name`.

    NOTE on scope: HUF does not currently maintain a general app-level registry of
    "every whitelisted function this app exposes" (no scan of api.py / **/*.py for
    @frappe.whitelist()-decorated functions). The only safe, existing enumeration
    surface available in this codebase is the app's own `huf_tools` hook entries
    (see huf.ai.tool_registry.get_tools_by_app / _normalize_hook_tools), which is
    exactly the same source `declared_actions_for_app` reads from Agent Tool Function
    records.

    So in practice this function re-resolves each huf_tools-declared function_path via
    `get_function_metadata(..., require_whitelisted=True)` and returns descriptors for
    those that verify as actually whitelisted right now (catching drift between the
    hook declaration and the current whitelisting state of the code). It does not
    invent filesystem/AST scanning to find whitelisted functions that have no
    huf_tools declaration at all -- building that would require a new app-level
    function registry that doesn't exist yet in this codebase.
    """
    if not app_name:
        return []

    descriptors = []
    for function_path in _iter_declared_function_paths(app_name):
        if len(descriptors) >= limit:
            break

        try:
            metadata = get_function_metadata(function_path, require_whitelisted=True)
        except frappe.PermissionError:
            # Declared in huf_tools but not actually whitelisted right now; skip.
            continue
        except Exception:
            # Any other resolution failure (bad path, import error, etc.) - skip, log-only.
            frappe.logger("huf").warning(
                f"discover_whitelisted_actions_for_app: could not resolve '{function_path}' for app '{app_name}'"
            )
            continue

        descriptors.append(
            make_capability_descriptor(
                kind="action",
                source_app=app_name,
                source_type="framework_discovered",
                source_key=function_path,
                title=metadata.get("function_name") or function_path,
                description=metadata.get("docstring"),
                function_path=function_path,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        p["fieldname"]: {"type": p["type"], "description": p.get("description", "")}
                        for p in metadata.get("parameters", [])
                    },
                    "required": [p["fieldname"] for p in metadata.get("parameters", []) if p.get("required")],
                },
                allow_guest=bool(metadata.get("allow_guest")),
                visibility="normal",
                actionability="actionable_now",
                confidence=0.7,
            )
        )

    return descriptors


def search_app_actions(app_name, query="", limit=50):
    """Merge declared + discovered actions for `app_name`, de-duplicated by function_path.

    Declared (huf_tools-synced) descriptors win over framework-discovered ones when both
    resolve to the same function_path. If `query` is non-empty, results are filtered by a
    case-insensitive substring match against title, function_path, or description.
    """
    declared = declared_actions_for_app(app_name)
    discovered = discover_whitelisted_actions_for_app(app_name)

    by_function_path = {}
    order = []

    for descriptor in declared + discovered:
        key = descriptor.get("function_path") or descriptor.get("source_key")
        if key not in by_function_path:
            order.append(key)
            by_function_path[key] = descriptor
        elif descriptor.get("source_type") == "declared":
            # Declared wins over a previously-seen discovered entry for the same function.
            by_function_path[key] = descriptor

    merged = [by_function_path[key] for key in order]

    if query:
        needle = query.strip().lower()
        if needle:
            def _matches(descriptor):
                haystacks = (
                    descriptor.get("title") or "",
                    descriptor.get("function_path") or "",
                    descriptor.get("description") or "",
                )
                return any(needle in haystack.lower() for haystack in haystacks)

            merged = [descriptor for descriptor in merged if _matches(descriptor)]

    return merged[:limit]


def describe_app_action(capability_id):
    """Resolve a single action capability descriptor by its capability_id.

    capability_id format: "action:{app}:{source_key}" (see build_capability_id).
    Raises frappe.DoesNotExistError if no matching action is found.
    """
    if not capability_id or capability_id.count(":") < 2:
        raise frappe.DoesNotExistError(_("Invalid capability id: {0}").format(capability_id))

    kind, app_name, source_key = capability_id.split(":", 2)
    if kind != "action":
        raise frappe.DoesNotExistError(_("Not an action capability id: {0}").format(capability_id))

    for descriptor in search_app_actions(app_name, query=""):
        if descriptor.get("id") == capability_id or build_capability_id(
            "action", app_name, descriptor.get("source_key")
        ) == capability_id:
            return descriptor

    raise frappe.DoesNotExistError(_("Action capability not found: {0}").format(capability_id))
