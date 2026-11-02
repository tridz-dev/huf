"""Frappe ecosystem detection for channel handoff adapters.

``get_ecosystem_apps()`` reports, for each known sibling app, whether it is installed on this site,
its version, and whether a WhatsApp handoff adapter is available for it.
"""

from __future__ import annotations

from typing import Any

import frappe

ECOSYSTEM_APPS = ("crm", "erpnext", "helpdesk", "lms", "ravan")


def _app_version(app: str) -> str | None:
	try:
		return str(frappe.get_attr(f"{app}.__version__"))
	except Exception:
		return None


def _adapter_available(app: str) -> bool:
	from huf.ai.channels import adapters

	return adapters.adapter_available_for_app(app)


def get_ecosystem_apps() -> dict[str, dict[str, Any]]:
	"""``{app: {installed, version, enabled_for_whatsapp}}`` for crm, erpnext, helpdesk, lms, ravan."""
	installed_apps = set(frappe.get_installed_apps())
	out: dict[str, dict[str, Any]] = {}
	for app in ECOSYSTEM_APPS:
		installed = app in installed_apps
		out[app] = {
			"installed": installed,
			"version": _app_version(app) if installed else None,
			"enabled_for_whatsapp": bool(installed and _adapter_available(app)),
		}
	return out


@frappe.whitelist()
def get_ecosystem() -> dict[str, dict[str, Any]]:
	"""Whitelisted wrapper for the Connections screen (admins only)."""
	from huf.ai.channels.api import _require_manage

	_require_manage()
	return get_ecosystem_apps()
