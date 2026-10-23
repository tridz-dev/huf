# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Shared doctype security guards for tool handlers.

This module centralizes the deny-by-default doctype checks used across
both huf/ai/tools/frappe_generic.py and huf/ai/handlers/ (crud.py, tool_functions.py)
to ensure consistent, auditable doctype access control from a single location.
"""

import json

import frappe

#: Exact doctype names (case-insensitive) that are never accessible through
#: generic tool surfaces, regardless of the caller's roles. These are either
#: security-sensitive (User, Role, *Script, Property Setter, File — which
#: guards arbitrary file records, not just literal uploads) or would let an
#: agent read/manufacture privilege (Role Profile).
_DENYLISTED_DOCTYPES = {
	"user",
	"role",
	"role profile",
	"custom script",
	"server script",
	"property setter",
	"file",
}

#: Doctype name PREFIXES (case-insensitive) that are denied wholesale, since
#: individual doctype names under these families change across versions/apps
#: (e.g. "OAuth Client", "OAuth Bearer Token", "Integration Request",
#: "Integration Service") and an allowlist-by-exact-name would miss new ones.
_DENYLISTED_PREFIXES = ("oauth", "integration")


def _error(msg: str) -> str:
	"""Format a security denial as JSON error."""
	return json.dumps({"success": False, "error": msg}, default=str)


def _check_doctype_allowed(doctype: str):
	"""Return ``(meta, None)`` if ``doctype`` may be accessed through tool
	surfaces, or ``(None, error_json_str)`` if it is denied.

	Deny-by-default on top of the explicit denylist: any doctype that does
	not exist, or whose meta cannot be loaded, is denied rather than silently
	passed through.

	Args:
		doctype: The doctype name to check.

	Returns:
		(meta, None) on allow, or (None, error_json_str) on deny.
	"""
	if not doctype or not isinstance(doctype, str):
		return None, _error("'doctype' is required")

	normalized = doctype.strip().lower()
	if normalized in _DENYLISTED_DOCTYPES:
		return None, _error(f"Access to doctype '{doctype}' is not permitted through this tool.")
	if normalized.startswith(_DENYLISTED_PREFIXES):
		return None, _error(f"Access to doctype '{doctype}' is not permitted through this tool.")

	try:
		if not frappe.db.exists("DocType", doctype):
			return None, _error(f"DocType '{doctype}' does not exist.")
		meta = frappe.get_meta(doctype)
	except Exception as e:
		return None, _error(f"Could not load DocType '{doctype}': {e}")

	# Single doctypes (e.g. System Settings, Global Defaults) hold one
	# site-wide configuration row apiece rather than a set of business
	# records - listing/creating/updating "records" for one makes no sense
	# in this tool's model and often exposes sensitive site config.
	if meta.issingle:
		return None, _error(f"'{doctype}' is a Single doctype and is not accessible through this tool.")

	return meta, None
