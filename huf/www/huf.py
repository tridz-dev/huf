import json

import frappe
import frappe.sessions
from frappe import _
from frappe.utils.telemetry import capture

no_cache = 1


def _safe_json_embed(data_dict) -> str:
	raw_json = frappe.as_json(data_dict, indent=None, separators=(",", ":"))
	# Escape HTML special characters to unicode escapes so JSON can be safely embedded in HTML templates
	safe_json = raw_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
	return json.dumps(safe_json)


def build_boot_context() -> dict:
	"""Standard HUF boot context: CSRF token + Guest-branching boot data.

	Extracted from get_context() below so any other renderer that needs the
	same "guest gets get_boot_data(), signed-in user gets sessions.get()"
	boot pattern can reuse it verbatim instead of re-deriving it -- notably
	huf.ai.app_portal_renderer.HufAppPortalRenderer (the per-app www/
	template registry, Phase 2 of the HufAppDeskPortalDelivery track), which
	is explicitly scoped to standardize on this exact pattern rather than
	inventing a second boot mechanism.

	Returns a plain dict with ``build_version``, ``boot`` (safely-embedded
	JSON string) and ``csrf_token`` -- the same three keys get_context()
	updates its context with.
	"""
	csrf_token = frappe.sessions.get_csrf_token()
	# Manually commit the CSRF token here
	frappe.db.commit()  # nosemgrep

	if frappe.session.user == "Guest":
		boot = frappe.website.utils.get_boot_data()
	else:
		try:
			boot = frappe.sessions.get()
		except Exception as e:
			raise frappe.SessionBootFailed from e

	# add server_script_enabled in boot
	if "server_script_enabled" in frappe.conf:
		enabled = frappe.conf.server_script_enabled
	else:
		enabled = True
	boot["server_script_enabled"] = enabled

	boot_json = _safe_json_embed(boot)

	return {
		"build_version": frappe.utils.get_build_version(),
		"boot": boot_json,
		"csrf_token": csrf_token,
	}


def get_context(context):
	context.update(build_boot_context())
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return json.loads(get_boot())


def get_boot():
	try:
		boot = frappe.sessions.get()
	except Exception as e:
		raise frappe.SessionBootFailed from e

	boot["push_relay_server_url"] = frappe.conf.get("push_relay_server_url")
	return _safe_json_embed(boot)