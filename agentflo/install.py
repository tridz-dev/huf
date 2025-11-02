# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for AgentFlo app
"""

import frappe


def after_install():
	"""
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	"""
	try:
		import litellm
		frappe.msgprint("✅ LiteLLM is installed and ready to use.")
	except ImportError:
		frappe.msgprint(
			"⚠️ LiteLLM package not found. "
			"Please run 'bench setup requirements' to install dependencies, "
			"then restart your site with 'bench restart'.",
			indicator="orange",
			title="Dependency Missing"
		)

