# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Permission envelope analyser for the Procedure/Flow graph IR (T-14).

This module has exactly two jobs, and they are not interchangeable:

1. STATIC PASS (``compute_static_envelope`` / ``static_tool_closure``): walk a compiled IR
   graph -- including nodes only reachable via ``foreach.config.body`` and
   ``parallel.config.branches``, per spec/graph-ir.md section 6 -- and report the READ /
   WRITE / HTTP / CODE surface the graph *declares*. This is a pre-activation review aid: a
   human or T-24's validator can look at it before the graph ever runs. It is derived purely
   from the graph document; it never touches ``frappe.db`` or the current user.

2. RUNTIME ENFORCEMENT (``authorize_tool_call``): the *only* function in this module (or
   that should ever be called by an executor) that is allowed to decide whether a specific
   ``tool.call`` node may actually execute right now, for a specific user, on a live site.

Invariant I1 (PLAN.md ss3): effective authority is always the INTERSECTION of

    user AND agent AND procedure envelope AND tool AND execution profile

never a union, and a procedure never grants authority its caller (the user, the Agent) does
not independently already hold. Invariant I2 is the reason this module is split the way it
is: "compile-time analysis never replaces runtime enforcement -- both always run." The
static envelope computed here is a ceiling, never a grant.

To make I2 structurally hard to violate, ``authorize_tool_call``:

  * has no parameter, flag, or code path that skips the live ``frappe.has_permission`` /
    ``PermissionAwareToolRegistry`` check -- there is no "trust the envelope" fast path to
    reach for by accident;
  * returns ``None`` and raises on denial, rather than returning a boolean a caller could
    silently ignore or invert;
  * re-derives the tool's own required permission via ``classify_tool`` and checks it
    against the envelope *in addition to* the live check, so a caller cannot satisfy I1 by
    presenting a stale or hand-built envelope that happens to say "yes" -- the live leg
    always runs regardless of what the static leg concluded.

Any new code path that authorizes a tool.call node by reading ``permission_envelope`` alone,
without going through ``authorize_tool_call`` (and therefore without a live
``frappe.has_permission`` call), is a defect, not an optimisation (T-14 warning, PLAN.md).

This module builds on ``huf.ai.tool_registry.PermissionAwareToolRegistry`` -- its
``TOOL_PERMISSIONS`` map and its per-tool gating classmethods (``_can_use_tool``,
``_allows_code_execution``, ``_allows_ssh_execution``, ``_allows_docker_execution``,
``_allows_ask_user``, ``_allows_document_artifact_tools``, the last two of which already
call ``huf.ai.capabilities.capability_enabled``) -- rather than inventing a parallel,
Procedure-specific authorization model.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Iterable, Iterator

import frappe

from huf.ai.tool_registry import PermissionAwareToolRegistry

TOOL_DOCTYPE = "Agent Tool Function"

# ptypes that count as "write" for envelope-bucketing purposes. Matches the mutating side
# of PermissionAwareToolRegistry.TOOL_PERMISSIONS (write/create/delete/submit/cancel); "read"
# is the only non-mutating ptype the registry knows about.
_WRITE_PTYPES = {"write", "create", "delete", "submit", "cancel"}

# Node-type-specific successor fields, per spec/graph-ir.md section 2. Every node also has
# optional "next" / "on_error", handled unconditionally below.
_HTTP_TOOL_TYPES = {"GET", "POST"}
_CODE_TOOL_TYPES = {"Code Execution"}


# --------------------------------------------------------------------------------------
# Static pass
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ToolPermission:
	"""The declared permission shape of a single ``tool.call`` node's ``tool_id``.

	``ptype`` / ``doctype`` describe a document-permission requirement (e.g. "read" on
	"Sales Invoice"); either may be ``None`` for a tool with no doctype surface (a pure
	HTTP or code-execution tool, or a conversation-scoped tool). ``http`` / ``code`` flag
	external-call and code-execution surface independently, since a tool can carry more
	than one kind of surface in principle even though today's registry types do not mix
	them.
	"""

	ptype: str | None
	doctype: str | None
	http: bool = False
	code: bool = False


ToolClassifier = Callable[[str], ToolPermission]


def default_tool_classifier(tool_id: str) -> ToolPermission:
	"""Resolve ``tool_id`` to its permission shape via the ``Agent Tool Function`` doctype.

	Reuses exactly the mapping ``PermissionAwareToolRegistry`` uses at runtime
	(``required_permission`` if explicitly set on the tool, else
	``TOOL_PERMISSIONS[tool.types]``) so the static pass and the runtime registry can never
	disagree about what a given tool type requires.
	"""
	tool_doc = frappe.get_cached_doc(TOOL_DOCTYPE, tool_id)
	ttype = tool_doc.types
	ptype = tool_doc.required_permission or (
		PermissionAwareToolRegistry.TOOL_PERMISSIONS.get(ttype, {}).get("permission")
	)
	doctype = getattr(tool_doc, "reference_doctype", None) or None
	return ToolPermission(
		ptype=ptype,
		doctype=doctype,
		http=ttype in _HTTP_TOOL_TYPES,
		code=ttype in _CODE_TOOL_TYPES,
	)


def _entry_roots(graph: dict) -> list[str]:
	entry = graph["entry"]
	return list(entry) if isinstance(entry, list) else [entry]


def iter_reachable_nodes(graph: dict) -> Iterator[dict]:
	"""Yield every node reachable from ``graph["entry"]``, exactly once each.

	Traverses every control-flow pointer the IR defines (spec/graph-ir.md section 2):
	``next``, ``on_error``, ``condition.on_true``/``on_false``,
	``router.llm.options[].node_id``/``default``, ``human.approval``'s three routing
	fields, and -- the part a naive main-chain-only walk misses -- every node id listed in
	``foreach.config.body`` and every branch of ``parallel.config.branches``. Those nested
	nodes are not reachable via ``next`` from the main chain (the spec forbids a node being
	reachable from two places), so they must be seeded into the walk directly or the
	envelope under-reports exactly the tool.call nodes doing the most repeated work.
	"""
	nodes_by_id = {node["id"]: node for node in graph.get("nodes", [])}
	visited: set[str] = set()
	worklist: list[str | None] = list(_entry_roots(graph))

	while worklist:
		node_id = worklist.pop()
		if node_id is None or node_id in visited:
			continue
		visited.add(node_id)
		node = nodes_by_id.get(node_id)
		if node is None:
			continue
		yield node

		config = node.get("config") or {}
		ntype = node.get("type")

		worklist.append(node.get("next"))
		worklist.append(node.get("on_error"))

		if ntype == "condition":
			worklist.append(config.get("on_true"))
			worklist.append(config.get("on_false"))
		elif ntype == "router.llm":
			for option in config.get("options", []) or []:
				worklist.append(option.get("node_id"))
			worklist.append(config.get("default"))
		elif ntype == "human.approval":
			worklist.append(config.get("approve_next"))
			worklist.append(config.get("reject_next"))
			worklist.append(config.get("timeout_next"))
		elif ntype == "foreach":
			worklist.extend(config.get("body", []) or [])
		elif ntype == "parallel":
			for branch in config.get("branches", []) or []:
				worklist.extend(branch)


def static_tool_closure(graph: dict) -> set[str]:
	"""The complete set of ``tool_id`` values invocable by this graph (spec section 6).

	Knowable by static inspection alone, before the graph is ever activated (I3). Does not
	include ``agent.run`` / ``router.llm`` dispatch targets -- those are the declared points
	where dispatch is dynamic and cannot appear in a Procedure graph at all (I4).
	"""
	return {
		node["config"]["tool_id"]
		for node in iter_reachable_nodes(graph)
		if node.get("type") == "tool.call" and node.get("config", {}).get("tool_id")
	}


def compute_static_envelope(
	graph: dict,
	classify_tool: ToolClassifier = default_tool_classifier,
) -> dict:
	"""Compute the declared ``permission_envelope`` (spec/graph-ir.md section 3) for ``graph``.

	Returns ``{"read": [...], "write": [...], "http": "none"|[...], "code": "none"|[...]}``,
	matching the IR's own envelope shape byte-for-byte (including the "none" sentinel
	instead of an empty list, per the spec's rationale for a greppable "no external access"
	state). This is a DECLARATION, not an authorization decision -- see module docstring
	and ``authorize_tool_call``.
	"""
	read_doctypes: set[str] = set()
	write_doctypes: set[str] = set()
	http_tool_ids: set[str] = set()
	code_tool_ids: set[str] = set()

	for node in iter_reachable_nodes(graph):
		if node.get("type") != "tool.call":
			continue
		tool_id = node.get("config", {}).get("tool_id")
		if not tool_id:
			continue
		perm = classify_tool(tool_id)
		if perm.doctype and perm.ptype == "read":
			read_doctypes.add(perm.doctype)
		elif perm.doctype and perm.ptype in _WRITE_PTYPES:
			write_doctypes.add(perm.doctype)
		if perm.http:
			http_tool_ids.add(tool_id)
		if perm.code:
			code_tool_ids.add(tool_id)

	return {
		"read": [{"doctype": d} for d in sorted(read_doctypes)],
		"write": [{"doctype": d} for d in sorted(write_doctypes)],
		"http": sorted(http_tool_ids) if http_tool_ids else "none",
		"code": sorted(code_tool_ids) if code_tool_ids else "none",
	}


# --------------------------------------------------------------------------------------
# Runtime enforcement (I1 intersection)
# --------------------------------------------------------------------------------------


def envelope_declares(envelope: dict, *, ptype: str, doctype: str) -> bool:
	"""True when ``envelope`` declares ``ptype`` access to ``doctype``.

	Pure static-declaration lookup -- reads a dict, touches nothing live. Exposed for T-24's
	validator and for tests that need to assert on the *declaration* itself. Deliberately
	NOT sufficient on its own to authorize anything at runtime: see ``authorize_tool_call``,
	which is the only function that may make that call, and which always runs a live check
	in addition to (never instead of) this one.
	"""
	bucket = "read" if ptype == "read" else "write" if ptype in _WRITE_PTYPES else None
	if bucket is None:
		return False
	return any(entry.get("doctype") == doctype for entry in envelope.get(bucket, []))


def authorize_tool_call(
	*,
	tool_id: str,
	user: str,
	agent_doc,
	envelope: dict,
	model_name: str | None = None,
	classify_tool: ToolClassifier = default_tool_classifier,
) -> None:
	"""Authorize one ``tool.call`` node's execution, or raise. This is I1, enforced.

	Effective authority is the intersection of:

	  * PROCEDURE ENVELOPE -- ``tool_id``'s own declared requirement must fall inside the
	    compiled ``permission_envelope`` (``envelope_declares``). A graph that reaches this
	    check with a tool outside its own declared envelope should already have been
	    rejected by T-24's static validator; this is a defence-in-depth re-check, not the
	    primary gate.
	  * USER, AGENT, TOOL, EXECUTION PROFILE -- delegated verbatim to
	    ``PermissionAwareToolRegistry``'s own per-tool gates, which end in a live
	    ``frappe.has_permission`` call and already fold in ``capability_enabled`` for the
	    ask_user / document-artifact tool families. This leg is unconditional: it runs
	    every time, with no parameter anywhere in this function's signature that could skip
	    it. That is what makes I2 -- "compile-time analysis never replaces runtime
	    enforcement" -- true of this function by construction rather than by caller
	    discipline.

	Raises ``frappe.PermissionError`` (via ``frappe.throw``) on any failed leg. Returns
	``None`` on success -- callers cannot mistake "didn't raise" for "returned True" and
	then invert or discard it; the only two outcomes are "execution may proceed" (no
	exception) and "it may not" (exception propagates).
	"""
	perm = classify_tool(tool_id)

	if perm.doctype and perm.ptype:
		if not envelope_declares(envelope, ptype=perm.ptype, doctype=perm.doctype):
			frappe.throw(
				f"Tool {tool_id!r} requires {perm.ptype!r} on {perm.doctype!r}, which is "
				"outside this procedure's compiled permission envelope.",
				frappe.PermissionError,
			)
	if perm.http and envelope.get("http") == "none":
		frappe.throw(
			f"Tool {tool_id!r} performs HTTP access, which this procedure's envelope "
			"declares as 'none'.",
			frappe.PermissionError,
		)
	if perm.code and envelope.get("code") == "none":
		frappe.throw(
			f"Tool {tool_id!r} performs code execution, which this procedure's envelope "
			"declares as 'none'.",
			frappe.PermissionError,
		)

	# The live leg. Always runs. No flag skips it.
	tool_doc = frappe.get_cached_doc(TOOL_DOCTYPE, tool_id)
	live_ok = (
		PermissionAwareToolRegistry._can_use_tool(tool_doc, user)
		and PermissionAwareToolRegistry._allows_code_execution(tool_doc, agent_doc, user)
		and PermissionAwareToolRegistry._allows_ssh_execution(tool_doc, agent_doc, user)
		and PermissionAwareToolRegistry._allows_docker_execution(tool_doc, user)
		and PermissionAwareToolRegistry._allows_ask_user(tool_doc, agent_doc, model_name)
		and PermissionAwareToolRegistry._allows_document_artifact_tools(tool_doc, agent_doc, model_name)
	)
	if not live_ok:
		agent_name = getattr(agent_doc, "name", agent_doc)
		frappe.throw(
			f"User {user!r} / agent {agent_name!r} does not currently hold live permission "
			f"to call tool {tool_id!r} (I1: intersection of user, agent, tool and execution "
			"profile -- independent of what the compiled envelope declares).",
			frappe.PermissionError,
		)
