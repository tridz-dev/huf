"""
Canvas Editor Portal Page Context
Provides context and includes Frappe JS for portal page
"""

import frappe
from frappe import _


def get_context(context):
	"""Get context for canvas editor portal page"""
	# Extract slug from URL
	slug = frappe.form_dict.get('slug')
	
	if not slug:
		frappe.throw(_("Canvas slug is required"), frappe.NotFound)
	
	# Verify canvas exists
	try:
		canvas = frappe.get_doc("Canvas", {"slug": slug})
	except frappe.DoesNotExistError:
		frappe.throw(_("Canvas not found: {0}").format(slug), frappe.NotFound)
	
	# Get agent info if assigned
	agent_info = None
	if canvas.agent:
		try:
			agent_doc = frappe.get_doc("Agent", canvas.agent)
			agent_info = {
				"name": agent_doc.agent_name,
				"description": agent_doc.description
			}
		except frappe.DoesNotExistError:
			pass
	
	# Include Frappe web bundle for API calls
	context.include_frappe_js = True
	
	# Add canvas and agent info to context
	context.canvas_slug = slug
	context.canvas_title = canvas.title
	context.agent_name = agent_info.get("name") if agent_info else None
	
	# CSRF token for API calls
	context.csrf_token = frappe.sessions.get_csrf_token()
	
	return context
