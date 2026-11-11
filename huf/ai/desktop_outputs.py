# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Desktop output upload and the Skills & Agents search (DesktopRemoteSessionsAndOffice R6, R3, section 9.11).

``upload_desktop_output`` is callable only by a desktop that presents its lease secret (a web session of
the same user has none) and only into a conversation hosted by that device. It creates an ``Artifact``;
binary files are attached as a private ``File`` and the artifact content is a small JSON pointer.
"""

import json

import frappe
from frappe import _

from huf.ai import desktop_executor as dx
from huf.ai import desktop_output_rules as rules


def _deny(msg):
	frappe.throw(msg, frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def upload_desktop_output(
	executor_id=None, conversation=None, filename=None, content_b64=None, lease_secret=None
):
	"""Create an Artifact in a desktop-hosted conversation from bytes the desktop uploads."""
	user = dx._require_user()
	lease = dx._get_lease(dx._validate_executor_id(executor_id)) if executor_id else None
	if (
		not lease
		or lease.get("user") != user
		or not dx.secret_matches(lease, dx.presented_secret(lease_secret))
	):
		_deny(_("A valid desktop lease secret is required."))
	conv = (
		frappe.db.get_value(
			"Agent Conversation",
			conversation,
			["name", "owner", "execution_host", "host_device_id"],
			as_dict=True,
		)
		if conversation
		else None
	)
	if (
		not conv
		or conv.owner != user
		or conv.execution_host != "desktop"
		or conv.host_device_id != lease.get("device_id")
	):
		# Same result for a missing and for someone else's conversation (no existence leak); the lease is valid so
		# this is a terminal per-conversation outcome, not an auth failure.
		return {
			"ok": False,
			"code": "not_hosted",
			"message": _("This conversation is not hosted by this desktop."),
		}
	try:
		name, ext, content_type, artifact_type, data, text = rules.validate_upload(filename, content_b64)
	except rules.UploadRejected as e:
		return {"ok": False, "code": e.code, "message": str(e)}

	doc = frappe.get_doc(
		{
			"doctype": "Artifact",
			"title": name[:140],
			"artifact_type": artifact_type,
			"language": ext,
			"conversation": conv.name,
			"content": text if text is not None else "",
		}
	)
	doc.insert(ignore_permissions=True)
	file_url = None
	if text is None:
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": name,
				"content": data,
				"is_private": 1,
				"attached_to_doctype": "Artifact",
				"attached_to_name": doc.name,
			}
		).insert(ignore_permissions=True)
		file_url = f.file_url
		doc.content = json.dumps(
			{"file_url": file_url, "filename": name, "content_type": content_type, "size": len(data)}
		)
		doc.save(ignore_permissions=True)
	return {
		"ok": True,
		"artifact": doc.name,
		"file_url": file_url,
		"size": len(data),
		"content_type": content_type,
	}


@frappe.whitelist()
def search_skills_and_agents(query=None, kind="all", limit=50):
	"""Search over agents and skills for the Skills & Agents box.
	Rows: ``{kind, name, id, description, origin?, enabled}``. Agents come from ``frappe.get_list`` (the
	Agent permission query: owner / allowed users / roles, enabled, non-system). Skills carry no
	per-user permission (the Skill doctype is System Manager only and the rest of the app lists them
	to every user through ``get_skill_options``), so only ``Active`` skills are listed."""
	if kind not in ("all", "agent", "skill"):
		kind = "all"
	items = []
	if kind in ("all", "agent"):
		for a in frappe.get_list(
			"Agent",
			filters={"disabled": 0},
			fields=["name", "agent_name", "description"],
			order_by="modified desc",
			limit_page_length=500,
		):
			items.append(
				{
					"kind": "agent",
					"name": a.agent_name or a.name,
					"id": a.name,
					"description": a.description or "",
				}
			)
	if kind in ("all", "skill"):
		for s in frappe.get_all(
			"Skill",
			filters={"status": "Active"},
			fields=["name", "skill_name", "title", "description", "source_type"],
			order_by="modified desc",
			limit_page_length=500,
		):
			items.append(
				{
					"kind": "skill",
					"name": s.skill_name or s.name,
					"id": s.name,
					"description": s.description or s.title or "",
					"origin": s.source_type,
					"enabled": True,
				}
			)
	return rules.rank_catalog(items, query, kind, limit)
