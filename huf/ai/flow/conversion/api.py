from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import now_datetime


# ---------------------------------------------------------------------------
# Flow -> Procedure conversion (T-52)
#
# "Flow is what you draw, Procedure is what it compiles to -- the same picture
# at two stages." The determinism check, entry rewiring and Procedure-graph
# compilation live in huf.ai.procedure.conversion (frappe-free, unit tested on
# its own); this layer only adds permission checks and the Agent Procedure
# creation, following the same whitelisted-endpoint shape as the rest of this
# module.
# ---------------------------------------------------------------------------


def _load_flow_graph(flow_id: str) -> tuple[frappe.Document, dict]:
	doc = frappe.get_doc("Flow Definition", flow_id)
	defn = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	if not isinstance(defn, dict):
		frappe.throw(_("Flow '{0}' has no valid definition to convert").format(flow_id))
	return doc, defn


@frappe.whitelist()
def analyze_flow_conversion(flow_id: str) -> dict:
	"""
	Read-only preview of converting a Flow to an Agent Procedure. Creates nothing.

	Args:
	    flow_id: Flow Definition name

	Returns:
	    dict -- either {"convertible": False, "reason": "..."} or
	    {"convertible": True, "reads": [...], "writes": [...],
	     "atomic_operations": N, "estimated_round_trip_reduction_pct": N}
	"""
	from huf.ai.flow.app_scope.api_guards import guard_huf_flow
	guard_huf_flow(flow_id)
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.procedure.conversion import analyze_conversion

	_doc, flow_graph = _load_flow_graph(flow_id)
	result = analyze_conversion(flow_graph)

	if not result.convertible:
		return {"convertible": False, "reason": result.reason}

	return {"convertible": True, **result.summary.as_dict()}


@frappe.whitelist(methods=["POST"])
def convert_flow_to_procedure(flow_id: str, procedure_id: str | None = None) -> dict:
	"""
	Convert a deterministic Flow into a Draft Agent Procedure.

	Refuses -- with a specific reason, no partial conversion -- for any flow that is
	not structurally deterministic (contains an ``agent.run``, ``router.llm`` or
	``human.approval`` step) or that does not itself validate. The created record is
	always ``tier="Draft"``, ``status="Draft"`` -- this endpoint never activates a
	procedure (I8); a human reviews and enables it separately.

	Args:
	    flow_id: Flow Definition to convert
	    procedure_id: Logical procedure id to create/append a version to. Defaults to
	        ``"{flow_id}-procedure"``. Re-converting the same flow under the same
	        procedure_id creates a new, immutable version (T-20), it never edits one.

	Returns:
	    dict with the created Agent Procedure's name/procedure_id/version, plus the
	    same reads/writes/estimated-reduction summary as analyze_flow_conversion.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_huf_flow
	guard_huf_flow(flow_id)
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Agent Procedure", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.procedure.conversion import analyze_conversion

	flow_doc, flow_graph = _load_flow_graph(flow_id)
	result = analyze_conversion(flow_graph)

	if not result.convertible:
		frappe.throw(result.reason, title=_("Flow Is Not Convertible"))

	resolved_procedure_id = procedure_id or f"{flow_id}-procedure"

	procedure = frappe.get_doc(
		{
			"doctype": "Agent Procedure",
			"procedure_id": resolved_procedure_id,
			"procedure_name": _("{0} (from Flow)").format(flow_doc.flow_name or flow_id),
			"definition_json": frappe.as_json(result.procedure_graph),
			"tier": "Draft",
			"status": "Draft",
			"provenance": frappe.as_json(
				{
					"source": "flow_conversion",
					"source_flow_id": flow_id,
					"source_flow_fingerprint": flow_graph.get("fingerprint"),
					"converted_by": frappe.session.user,
					"converted_at": str(now_datetime()),
				}
			),
		}
	)
	procedure.insert()

	return {
		"name": procedure.name,
		"procedure_id": procedure.procedure_id,
		"version": procedure.version,
		"status": procedure.status,
		"tier": procedure.tier,
		**result.summary.as_dict(),
	}
