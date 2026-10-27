"""
Local MCP and managed-browser helpers for Huf Desktop (Desktop Local Capabilities H3).

Pure functions over the SANITISED, PINNED catalog (``desktop_executor.get_catalog``): no
Redis, no database, no Frappe import at module level, so both the executor (``dispatch``
pre-checks), the tool builder (``sdk_tools``) and the handlers (``tools.desktop_local``) can
share one definition of "what the model may see and call".

Naming
------
* A local MCP tool is exposed as ``lmcp__<server>__<tool>`` (server and tool are the
  catalog's normalised names, ``[a-z0-9_-]``). The prefix means a local tool can never
  collide with a server tool. A name over 64 characters (the smallest provider limit) is
  shortened with a hash of ``(server, tool)``; two different pairs that flatten to the same
  string get distinct, deterministic names.
* The managed browser server is published by the desktop under the catalog server name
  ``BROWSER_SERVER`` ("browser"). Its curated subset is exposed as ``lbrowser__<tool>``. It is
  never part of the generic MCP group, so ``desktop_mcp_find`` / ``desktop_mcp_call`` can never
  reach it (L28): ``browser_evaluate``, ``browser_run_code_unsafe`` and ``browser_file_upload``
  are not in the schema and are refused by ``dispatch`` even if a model names them.

Context budget (PLAN 4.4)
-------------------------
Eager expansion stops at the first tool that would exceed 16 tools OR about 8k tokens of
schema (chars / 4), in the catalog's order (which is the local per-server priority). Everything
after that is reachable through ``desktop_mcp_find`` and ``desktop_mcp_call``.
"""

import copy
import hashlib
import json
import re

MCP_TOOL_PREFIX = "lmcp__"
BROWSER_TOOL_PREFIX = "lbrowser__"
# The catalog server name under which the desktop publishes its managed Playwright server.
BROWSER_SERVER = "browser"

MAX_TOOL_NAME_CHARS = 64
MCP_EAGER_MAX_TOOLS = 16
MCP_EAGER_MAX_TOKENS = 8000
CHARS_PER_TOKEN = 4
MCP_FIND_MAX_RESULTS = 20
MCP_FIND_DEFAULT_RESULTS = 8
MAX_ERRORS_REPORTED = 5
MAX_ERROR_CHARS = 600

# PLAN 4.8. Anything not listed here is never exposed and never dispatched for the browser
# server (``browser_evaluate``, ``browser_run_code_unsafe``, ``browser_file_upload``,
# ``browser_network_request(s)`` and everything under ``--caps``).
CURATED_BROWSER_TOOLS = (
	"browser_navigate",
	"browser_navigate_back",
	"browser_snapshot",
	"browser_click",
	"browser_type",
	"browser_fill_form",
	"browser_select_option",
	"browser_press_key",
	"browser_wait_for",
	"browser_tabs",
	"browser_close",
	"browser_take_screenshot",
	"browser_console_messages",
)

# Keys the tool wrapper owns (run identity, pins, permissions). A tool whose top-level schema
# declares one of these would have that argument overwritten, so it is not expanded as its own
# tool: it stays reachable through ``desktop_mcp_call``, whose ``arguments`` object is nested.
RESERVED_ARGUMENT_NAMES = frozenset(
	{
		"agent_run_id",
		"conversation_id",
		"call_id",
		"agent_name",
		"ignore_permissions",
		"tool_name",
	}
)

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


# --------------------------------------------------------------------------
# Catalog views
# --------------------------------------------------------------------------


def agent_allowed(entry_agents, agent_name) -> bool:
	"""Per-agent narrowing published by the desktop: ``"any"`` or a list of agent names."""
	if entry_agents in (None, "any"):
		return True
	if not isinstance(entry_agents, list):
		return False
	return bool(agent_name) and str(agent_name) in entry_agents


def _has_external_ref(node) -> bool:
	"""True if any ``$ref`` in the schema points outside the document (never resolved)."""
	if isinstance(node, dict):
		for key, value in node.items():
			if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
				return True
			if _has_external_ref(value):
				return True
	elif isinstance(node, list):
		return any(_has_external_ref(v) for v in node)
	return False


def find_server(catalog, server):
	for entry in (catalog or {}).get("mcp") or []:
		if entry.get("server") == server:
			return entry
	return None


def find_tool(server_entry, tool):
	for entry in (server_entry or {}).get("tools") or []:
		if entry.get("name") == tool:
			return entry
	return None


def browser_enabled(catalog) -> bool:
	return bool(((catalog or {}).get("browser") or {}).get("enabled"))


def visible_mcp_tools(catalog, agent_name) -> list:
	"""``[(server_entry, tool_entry)]`` the model may use through the generic MCP group.

	Excludes the managed browser server, servers whose "agents allowed" list omits this agent,
	and tools whose schema needs an external ``$ref`` (never resolved, so never callable).
	"""
	out = []
	for server in (catalog or {}).get("mcp") or []:
		if server.get("server") == BROWSER_SERVER or not agent_allowed(server.get("agents"), agent_name):
			continue
		for tool in server.get("tools") or []:
			if _has_external_ref(tool.get("input_schema")):
				continue
			out.append((server, tool))
	return out


def curated_browser_tools(catalog, agent_name) -> list:
	"""``[(server_entry, tool_entry)]`` for the browser subset, in the curated order."""
	if not browser_enabled(catalog):
		return []
	server = find_server(catalog, BROWSER_SERVER)
	if not server or not agent_allowed(server.get("agents"), agent_name):
		return []
	by_name = {t.get("name"): t for t in server.get("tools") or []}
	return [
		(server, by_name[name])
		for name in CURATED_BROWSER_TOOLS
		if name in by_name and not _has_external_ref(by_name[name].get("input_schema"))
	]


# --------------------------------------------------------------------------
# Names and schemas
# --------------------------------------------------------------------------


def _short_hash(*parts) -> str:
	return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:8]


def unique_tool_name(prefix, server, tool, taken) -> str:
	"""A deterministic, provider-safe tool name for ``(server, tool)`` not in ``taken``.

	Adds the name to ``taken``. ``lmcp__a__b__c`` is ambiguous between (server ``a``, tool
	``b__c``) and (``a__b``, ``c``): the second one to ask gets a hash suffix, and the choice
	depends only on catalog order, so it is stable within a pinned run.
	"""
	base = f"{prefix}{server}__{tool}" if prefix == MCP_TOOL_PREFIX else f"{prefix}{tool}"
	candidates = []
	if len(base) <= MAX_TOOL_NAME_CHARS:
		candidates.append(base)
	suffix = "_" + _short_hash(prefix, server, tool)
	candidates.append(base[: MAX_TOOL_NAME_CHARS - len(suffix)].rstrip("_-") + suffix)
	for candidate in candidates:
		if candidate not in taken:
			taken.add(candidate)
			return candidate
	counter = 2
	while True:
		tail = f"{suffix}_{counter}"
		candidate = base[: MAX_TOOL_NAME_CHARS - len(tail)].rstrip("_-") + tail
		if candidate not in taken:
			taken.add(candidate)
			return candidate
		counter += 1


def _clean_schema_text(node, sanitize):
	"""Deep copy of a JSON schema with every ``description`` / ``title`` string sanitised."""
	if isinstance(node, dict):
		out = {}
		for key, value in node.items():
			if key in ("description", "title") and isinstance(value, str):
				out[key] = sanitize(value, 512)
			elif key in ("$id", "$schema", "$comment"):
				continue
			else:
				out[key] = _clean_schema_text(value, sanitize)
		return out
	if isinstance(node, list):
		return [_clean_schema_text(v, sanitize) for v in node]
	return node


def model_schema(tool_entry, sanitize) -> dict:
	"""The object schema shown to the model for a tool (text re-sanitised, root forced to object)."""
	schema = tool_entry.get("input_schema")
	if not isinstance(schema, dict) or not schema:
		return copy.deepcopy(_EMPTY_SCHEMA)
	clean = _clean_schema_text(schema, sanitize)
	if clean.get("type") != "object":
		# A non-object root cannot be a function-call argument set; fall back to no arguments.
		return copy.deepcopy(_EMPTY_SCHEMA)
	clean.setdefault("properties", {})
	return clean


def model_description(server_name, tool_entry, sanitize) -> str:
	"""``[local MCP: <server>] <description>``: the prefix marks the origin (T5), text is re-sanitised."""
	label = "local browser" if server_name == BROWSER_SERVER else f"local MCP: {server_name}"
	text = sanitize(tool_entry.get("description"), 512)
	head = f"[{label}]"
	return f"{head} {text}".strip() if text else head


def _schema_cost(name, description, schema) -> int:
	try:
		size = len(json.dumps(schema, separators=(",", ":")))
	except (TypeError, ValueError):
		size = 4096
	return (len(name) + len(description) + size) // CHARS_PER_TOKEN + 1


def _declares_reserved_argument(schema) -> bool:
	props = (schema or {}).get("properties") if isinstance(schema, dict) else None
	return isinstance(props, dict) and any(k in RESERVED_ARGUMENT_NAMES or k.startswith("_dx_") for k in props)


def plan_mcp_group(catalog, agent_name, sanitize, taken=None) -> dict:
	"""Split the visible local MCP tools into eager tools and the overflow.

	Returns ``{"eager": [spec], "overflow": [spec], "tokens": int}`` where a spec is
	``{name, server, tool, description, schema}`` (``name`` is None for overflow tools). Never
	raises on a malformed catalog entry: it is skipped.
	"""
	taken = set() if taken is None else taken
	eager, overflow, tokens, budget_full = [], [], 0, False
	for server, tool in visible_mcp_tools(catalog, agent_name):
		sname, tname = server.get("server"), tool.get("name")
		if not sname or not tname:
			continue
		description = model_description(sname, tool, sanitize)
		schema = model_schema(tool, sanitize)
		spec = {"server": sname, "tool": tname, "description": description, "schema": schema, "name": None}
		if budget_full or _declares_reserved_argument(schema):
			overflow.append(spec)
			continue
		name = unique_tool_name(MCP_TOOL_PREFIX, sname, tname, set(taken))
		cost = _schema_cost(name, description, schema)
		if len(eager) >= MCP_EAGER_MAX_TOOLS or tokens + cost > MCP_EAGER_MAX_TOKENS:
			budget_full = True
			overflow.append(spec)
			continue
		spec["name"] = unique_tool_name(MCP_TOOL_PREFIX, sname, tname, taken)
		tokens += cost
		eager.append(spec)
	return {"eager": eager, "overflow": overflow, "tokens": tokens}


def plan_browser_group(catalog, agent_name, sanitize, taken=None) -> list:
	"""Specs for the curated browser tools (no budget: about ten tools, no overflow)."""
	taken = set() if taken is None else taken
	specs = []
	for server, tool in curated_browser_tools(catalog, agent_name):
		tname = tool.get("name")
		specs.append(
			{
				"name": unique_tool_name(BROWSER_TOOL_PREFIX, server.get("server"), tname, taken),
				"server": server.get("server"),
				"tool": tname,
				"description": model_description(server.get("server"), tool, sanitize),
				"schema": model_schema(tool, sanitize),
			}
		)
	return specs


def find_matches(catalog, agent_name, query, server=None, limit=MCP_FIND_DEFAULT_RESULTS, sanitize=None) -> list:
	"""Search the visible local MCP tools by words in server, name and description."""
	words = [w for w in re.split(r"\s+", str(query or "").lower()) if w][:8]
	rows = []
	for srv, tool in visible_mcp_tools(catalog, agent_name):
		if server and srv.get("server") != server:
			continue
		hay = f"{srv.get('server')} {tool.get('name')} {tool.get('description')}".lower()
		if all(w in hay for w in words):
			rows.append((srv, tool))
		if len(rows) >= max(1, min(MCP_FIND_MAX_RESULTS, int(limit))):
			break
	return rows


# --------------------------------------------------------------------------
# Argument validation and the dispatch pre-check
# --------------------------------------------------------------------------


def validate_arguments(schema, arguments):
	"""Validate ``arguments`` against a catalog input schema.

	Returns ``None`` when valid, else ``("invalid_params" | "tool_unavailable", message)``. A
	schema that is not itself valid, or that needs an external reference, fails closed.
	"""
	from jsonschema import Draft202012Validator
	from jsonschema.exceptions import SchemaError
	from jsonschema.validators import validator_for

	if not isinstance(arguments, dict):
		return ("invalid_params", "arguments must be an object.")
	if not isinstance(schema, dict) or not schema:
		return None
	if _has_external_ref(schema):
		return ("tool_unavailable", "The tool's input schema uses external references and cannot be checked.")
	try:
		validator_cls = validator_for(schema, default=Draft202012Validator)
		validator_cls.check_schema(schema)
		errors = sorted(validator_cls(schema).iter_errors(arguments), key=lambda e: [str(p) for p in e.absolute_path])
	except SchemaError:
		return ("tool_unavailable", "The tool's input schema in the pinned catalog is not a valid JSON schema.")
	except Exception:  # noqa: BLE001 - a hostile schema must never raise into the tool loop
		return ("tool_unavailable", "The tool's input schema in the pinned catalog could not be evaluated.")
	if not errors:
		return None
	lines = []
	for error in errors[:MAX_ERRORS_REPORTED]:
		where = ".".join(str(p) for p in error.absolute_path)
		lines.append(f"{where or 'arguments'}: {str(error.message)[:200]}")
	message = "arguments do not match the tool's input schema: " + "; ".join(lines)
	if len(errors) > MAX_ERRORS_REPORTED:
		message += f" (and {len(errors) - MAX_ERRORS_REPORTED} more)"
	return ("invalid_params", message[:MAX_ERROR_CHARS])


def mcp_call_unavailable(catalog, params, agent_name):
	"""Server half of "never execute something else" for ``mcp.call`` (L11, L13, L14, L28).

	``catalog`` is the catalog PINNED to the run (None when unknown or expired). Returns
	``(code, message)`` or None when the call may be published.
	"""
	if catalog is None:
		return ("tool_unavailable", "The local MCP catalog pinned to this run is no longer available. Start a new run.")
	server_name, tool_name, arguments = params.get("server"), params.get("tool"), params.get("arguments")
	server = find_server(catalog, server_name)
	tool = find_tool(server, tool_name)
	if server is None or tool is None:
		return ("tool_unavailable", "That local MCP tool is not in the catalog pinned to this run.")
	if not agent_allowed(server.get("agents"), agent_name):
		return ("denied_by_policy", "This agent is not allowed to use that local MCP server on this computer.")
	if server_name == BROWSER_SERVER:
		if not browser_enabled(catalog):
			return ("tool_unavailable", "The local browser is not enabled on this computer.")
		if tool_name not in CURATED_BROWSER_TOOLS:
			return ("denied_by_policy", f"{tool_name} is not available to agents.")
	return validate_arguments(tool.get("input_schema"), arguments)
