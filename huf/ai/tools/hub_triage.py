"""
Hub triage tools — read-only discovery and routing helpers for agent hub scenarios.

These handlers let users discover existing agents and site capabilities to
route queries appropriately. Both tools enforce builder capability and return
plain dicts with no secrets.
"""

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
	"""Find existing agents matching a query and return ranked candidates.

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
			"query": str
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

	# Sort by score descending, cap at limit
	scored.sort(key=lambda x: x["score"], reverse=True)
	scored = scored[:limit]

	return {
		"matches": scored,
		"query": query,
	}


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
