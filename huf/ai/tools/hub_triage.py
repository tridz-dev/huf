"""
Hub triage tools — read-only discovery and routing helpers for agent hub scenarios.

These handlers let users discover existing agents and site capabilities to
route queries appropriately. Both tools enforce builder capability and return
plain dicts with no secrets.

Decision routing integration: find_existing_agents integrates with Decision Runtime
via the Hub Orchestrator Agent's Agent Routing binding (PLAN.md D7, §3.10).
"""

from __future__ import annotations

import frappe

from huf.ai.tools.builder import _require_builder_capability


# Common stopwords to exclude from scoring (all lowercase)
_STOPWORDS = {
	"a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
	"has", "he", "in", "is", "it", "its", "of", "on", "or", "that",
	"the", "to", "was", "will", "with", "me", "please", "report",
}


def _tokenize_query(query: str) -> list:
	"""Split query into lowercase tokens, filter stopwords, keep tokens >= 3 chars."""
	if not query:
		return []
	tokens = query.lower().split()
	return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _score_candidate(query_tokens: list, candidate_name: str, candidate_desc: str, tool_names: list) -> float:
	"""Score a candidate agent by token overlap with name, description, and tool names."""
	if not query_tokens:
		return 0.0

	# Combine all searchable text
	all_text = (
		(candidate_name or "").lower() + " " +
		(candidate_desc or "").lower() + " " +
		" ".join((t or "").lower() for t in tool_names)
	)

	# Count matching tokens
	matches = sum(1 for token in query_tokens if token in all_text)
	return float(matches) / len(query_tokens) if query_tokens else 0.0


def find_existing_agents(query: str, limit: int = 5) -> dict:
	"""Find existing agents matching a query, with optional Decision Runtime reranking.

	Integrates with the Hub Orchestrator Agent's Agent Routing decision binding (D7, §3.10)
	only when enabled. With no binding or kill switch off, output is byte-identical to pre-decide.

	Args:
		query: Search query (tokenized and scored against agent names, descriptions, and tools).
		limit: Max agents to return (capped at 10).

	Returns:
		{
			"matches": [
				{
					"agent_name": str,
					"description": str (truncated to 200 chars),
					"tools": [str, ...],
					"score": float
				},
				...
			],
			"query": str,
			"decision_hint": str | None (only if Advise decision ran),
			"decision_call": str | None (only if decision ran)
		}
	"""
	_require_builder_capability()

	# Enforce limit cap
	limit = min(limit, 10)

	# Get candidate agents (permission-filtered by get_list)
	try:
		candidates = frappe.get_list(
			"Agent",
			filters={"disabled": 0, "allow_chat": 1},
			fields=["name", "agent_name", "description"],
			limit_page_length=200,
		)
	except Exception:
		candidates = []

	query_tokens = _tokenize_query(query)
	scored = []

	tools_by_agent = {}
	try:
		for row in frappe.get_all(
			"Agent Tool",
			filters={"parent": ["in", [c.get("name") for c in candidates]], "parenttype": "Agent"},
			fields=["parent", "tool"],
			parent_doctype="Agent",
			limit_page_length=0,
		):
			tools_by_agent.setdefault(row["parent"], []).append(row["tool"])
	except Exception:
		tools_by_agent = {}

	# Build agent_id->name mapping (internal only, never exposed in result)
	agent_id_map = {}

	for cand in candidates:
		# Skip "Hub Orchestrator" agent
		if cand.get("agent_name") == "Hub Orchestrator":
			continue

		agent_name = cand.get("name")
		if not agent_name:
			continue

		tools = tools_by_agent.get(agent_name, [])

		# Score this candidate
		score = _score_candidate(
			query_tokens,
			cand.get("agent_name", ""),
			cand.get("description", ""),
			tools,
		)

		if score > 0:
			# Truncate description to 200 chars
			description = cand.get("description", "")
			if description and len(description) > 200:
				description = description[:200]

			scored.append({
				"agent_name": cand.get("agent_name"),
				"description": description,
				"tools": tools,
				"score": score,
			})
			# Keep agent_id mapping internal
			agent_id_map[cand.get("agent_name")] = agent_name

	# Sort by score descending, cap at limit
	scored.sort(key=lambda x: x["score"], reverse=True)
	scored = scored[:limit]

	# Base result (byte-identical to pre-decide when decision is off)
	result = {
		"matches": scored,
		"query": query,
	}

	# Apply Decision Runtime integration only if enabled
	try:
		result = _apply_agent_routing_decision(scored, agent_id_map, result)
	except Exception as e:
		# Log but don't break; decision integration is optional
		frappe.logger("huf").warning(f"Agent routing decision integration error: {e}")

	return result


def _apply_agent_routing_decision(scored_agents: list, agent_id_map: dict, result: dict) -> dict:
	"""Apply Agent Routing decision binding if configured on Hub Orchestrator Agent.

	PLAN.md §3.10: If the Hub Orchestrator Agent has an enabled Agent Routing binding,
	apply it to the authorized agent list. Early exit cheaply if kill switch is off or
	binding is not enabled (harness principle: zero overhead when disabled).

	Args:
		scored_agents: The base-scored agent list without agent_id exposed.
		agent_id_map: Internal mapping of agent_name -> agent_id for decision.
		result: The result dict to update with decision_call and hint only if decision ran.

	Returns:
		The updated result dict.
	"""
	from huf.ai.app_seeding.hub_orchestrator import HUB_AGENT_NAME
	from huf.ai.decision.agent_surfaces import decide_for_surface
	from huf.ai.decision.types import DecisionOrigin, Option

	# Check kill switch early (Agent Settings.decision_runtime_enabled)
	try:
		settings = frappe.get_single("Agent Settings")
		if not settings.decision_runtime_enabled:
			return result
	except Exception:
		# If settings not found or error reading, skip decision integration
		return result

	# Get Hub Orchestrator Agent doc
	try:
		hub_agent = frappe.get_doc("Agent", HUB_AGENT_NAME)
	except frappe.DoesNotExistError:
		# Hub Orchestrator not configured
		return result

	# Check for enabled Agent Routing binding early (cheap check before building candidates)
	if not _has_enabled_agent_routing_binding(hub_agent):
		return result

	# Build Option objects for candidates using internal agent_id_map
	candidates = tuple(
		Option(id=agent_id_map.get(agent["agent_name"], agent["agent_name"]),
		       description=agent.get("agent_name", ""))
		for agent in scored_agents
	)

	if not candidates:
		return result

	# Call decide_for_surface with Agent Routing surface
	# origin_type must be one of the Decision Call options: "Hub" (not "Hub Triage")
	origin = DecisionOrigin(
		origin_type="Hub",
		agent=HUB_AGENT_NAME,
		owner_user=frappe.session.user,
	)
	try:
		decision = decide_for_surface(
			hub_agent,
			surface="Agent Routing",
			candidates=candidates,
			state={},  # No context state for hub triage
			origin=origin,
			candidate_source=None,
			candidate_resolver_id=None,
			top_n=len(scored_agents),
			hint_kind="agents",
		)
	except Exception:
		# Decision integration failed; continue with base list
		return result

	if decision is None:
		# Off, Shadow (enqueued), or any error
		return result

	# Only add decision fields if decision actually returned (Advise or Enforce)
	if decision.decision_call:
		result["decision_call"] = decision.decision_call

	if decision.mode == "Advise":
		# Add hint to result
		if decision.hint:
			result["decision_hint"] = decision.hint
		return result

	if decision.mode == "Enforce":
		# Rerank the list to match selected_ids order
		if decision.selected_ids:
			# Build agent_name->agent map for reordering
			agent_by_name = {agent["agent_name"]: agent for agent in scored_agents}
			reranked = []
			for selected_id in decision.selected_ids:
				# Find matching agent by agent_name (reverse lookup from agent_id_map)
				for agent_name, agent_id in agent_id_map.items():
					if agent_id == selected_id:
						if agent_name in agent_by_name:
							reranked.append(agent_by_name[agent_name])
						break
			result["matches"] = reranked
		return result

	return result


def _has_enabled_agent_routing_binding(agent_doc: any) -> bool:
	"""Check if agent has an enabled Agent Routing decision binding.

	Args:
		agent_doc: The Agent document.

	Returns:
		True if enabled Agent Routing binding exists, False otherwise.
	"""
	bindings = agent_doc.get("decision_bindings") or []
	for binding in bindings:
		if (binding.get("surface") == "Agent Routing" and
		    binding.get("enabled") and
		    binding.get("mode") in ("Advise", "Enforce", "Shadow")):
			return True
	return False


def discover_site_capabilities(query: str, limit: int = 8) -> dict:
	"""Discover site capabilities (apps, reports, resources) matching a query.

	Args:
		query: Search query (tokenized and matched against reports and resource names).
		limit: Max reports to fetch (capped at 8).

	Returns:
		{
			"installed_apps": [{"app": str, "title": str}, ...],
			"reports": [
				{
					"name": str,
					"ref_doctype": str,
					"module": str,
					"report_type": str,
				},
				...
			],
			"resources": [
				{
					"app": str,
					"doctype": str,
				},
				...
			],
			"erpnext_installed": bool,
			"catalogue_matches": [str, ...],
		}
	"""
	_require_builder_capability()

	# Enforce limit cap
	limit = min(limit, 8)
	query_tokens = _tokenize_query(query)

	# Check ERPNext installation
	erpnext_installed = False
	try:
		erpnext_installed = "erpnext" in frappe.get_installed_apps()
	except Exception:
		pass

	# Get installed apps
	installed_apps = []
	try:
		from huf.ai.capability_discovery.apps import get_capability_apps
		app_list = get_capability_apps()
		# get_capability_apps returns list of dicts with 'app' and 'title' keys
		installed_apps = app_list if isinstance(app_list, list) else []
	except Exception:
		installed_apps = []

	# Get reports matching query
	reports = []
	if query_tokens:
		try:
			fields = ["name", "ref_doctype", "module", "report_type"]
			phrase = " ".join(query_tokens)
			reports = frappe.get_list(
				"Report",
				filters={"disabled": 0, "name": ["like", f"%{phrase}%"]},
				fields=fields,
				limit_page_length=limit,
			)
			if not reports:
				# Fall back to reports matching every token, then any token.
				for join in ("and", "or"):
					flt = [["name", "like", f"%{t}%"] for t in query_tokens]
					kw = {"filters": [["disabled", "=", 0]] + flt} if join == "and" else {
						"filters": {"disabled": 0}, "or_filters": flt}
					reports = frappe.get_list("Report", fields=fields, limit_page_length=limit, **kw)
					if reports:
						break
		except Exception:
			reports = []

	# Get resources per app
	resources = []
	apps_to_check = installed_apps[:6] if installed_apps else []
	for app_info in apps_to_check:
		app_name = app_info.get("app") if isinstance(app_info, dict) else str(app_info)
		try:
			from huf.ai.capability_discovery.resources import get_app_resources
			app_resources = get_app_resources(app_name, "recommended")
			if isinstance(app_resources, list):
				# Filter to resources matching query tokens and check read permission
				for resource in app_resources:
					if isinstance(resource, dict):
						doctype = resource.get("doctype_name") or resource.get("doctype")
						if not doctype:
							continue
						if query_tokens and not any(t in doctype.lower() for t in query_tokens):
							continue
						# Check read permission
						try:
							if frappe.has_permission(doctype, "read"):
								resources.append({
									"app": app_name,
									"doctype": doctype,
								})
						except Exception:
							pass
		except Exception:
			# Swallow per-app exceptions so one failure doesn't break output
			pass

	# Get ERPNext report catalogue matches
	catalogue_matches = []
	if erpnext_installed and query_tokens:
		try:
			from huf.ai.tools.erpnext_reports import REPORT_CATALOGUE
			for token in query_tokens:
				for module_reports in REPORT_CATALOGUE.values():
					for report_name in module_reports:
						if token in report_name.lower():
							if report_name not in catalogue_matches:
								catalogue_matches.append(report_name)
		except Exception:
			pass

	return {
		"installed_apps": installed_apps,
		"reports": reports,
		"resources": resources,
		"erpnext_installed": erpnext_installed,
		"catalogue_matches": catalogue_matches,
	}
