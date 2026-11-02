# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Default Memory Policy and Execution Profile presets seeded by the install and migrate hooks
(``huf.install`` re-exports both functions).
"""

import frappe

logger = frappe.logger("huf")


def create_default_memory_policies():
	"""Create default Memory Policy presets."""
	presets = [
		{"policy_name": "Conservative", "description": "Nothing is captured automatically. Memory is written only via explicit tool calls and always needs human approval before it's used, so it's a safe default for agents handling sensitive or high-stakes conversations.", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 1, "default_status": "Draft", "inject_mode": "Relevant Only", "max_records": 5, "token_budget": 1500, "auto_promote_to_knowledge": 0, "allow_agent_write": 0},
		{"policy_name": "Conversational", "description": "For chat agents that should remember users across sessions with minimal friction. Every run is reviewed in the background and captured facts/preferences are injected into every future conversation automatically, no approval step.", "scope_type": "Agent", "capture_mode": "Automatic", "approval_required": 0, "default_status": "Draft", "inject_mode": "Always", "max_records": 10, "token_budget": 2000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
		{"policy_name": "Research", "description": "For agents doing extended research or knowledge work. The agent proposes what's worth remembering after each run, retrieval is narrowed to what's relevant to the current turn, and a larger token budget supports longer-running context.", "scope_type": "Agent", "capture_mode": "Agent Suggested", "approval_required": 0, "default_status": "Active", "inject_mode": "Relevant Only", "max_records": 20, "token_budget": 4000, "auto_promote_to_knowledge": 0, "promotion_min_confidence": 0.5, "promotion_min_importance": 0.5, "allow_agent_write": 1},
		{"policy_name": "Operational", "description": "For task/ops agents where memory should stay out of the way. Nothing is captured or injected automatically — the agent can write memory via a tool call and pull it back only when it explicitly searches for it.", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 0, "default_status": "Active", "inject_mode": "Tool Only", "max_records": 10, "token_budget": 1000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
	]
	for preset in presets:
		if frappe.db.exists("Memory Policy", preset["policy_name"]):
			continue
		try:
			doc = frappe.new_doc("Memory Policy")
			doc.update(preset)
			doc.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				title="Memory Policy Creation",
				message=f"Error creating memory policy {preset['policy_name']}: {str(e)}",
			)

	frappe.db.commit()


def create_default_execution_profiles():
	"""Create default Execution Profile presets shipped with Huf."""
	profiles = [
		{
			"profile_name": "Restricted",
			"approval_mode": "Ask Every Time",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 30,
			"max_cpu_seconds": 30,
			"max_memory_mb": 256,
			"max_output_bytes": 1048576,
		},
		{
			"profile_name": "Trusted",
			"approval_mode": "Auto Approve",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 60,
			"max_cpu_seconds": 60,
			"max_memory_mb": 512,
			"max_output_bytes": 2097152,
		},
		{
			# The profile an "Execute code" Flow step starts with: runs on its own (nobody has to
			# approve each run), a private scratch folder, no network, small fixed limits.
			"profile_name": "Flow Scratch",
			"approval_mode": "Auto Approve",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 30,
			"max_cpu_seconds": 30,
			"max_memory_mb": 256,
			"max_output_bytes": 262144,
		},
		{
			"profile_name": "Blocked",
			"approval_mode": "Never Allow",
			"is_builtin": 1,
			"filesystem_policy": "None",
			"max_wall_time_s": 5,
			"max_cpu_seconds": 5,
			"max_memory_mb": 128,
			"max_output_bytes": 65536,
		},
	]
	for profile in profiles:
		if frappe.db.exists("Execution Profile", profile["profile_name"]):
			continue
		try:
			doc = frappe.new_doc("Execution Profile")
			doc.update(profile)
			doc.insert(ignore_permissions=True)
		except Exception as e:
			logger.warning(
				f"Failed to create default execution profile {profile['profile_name']}: {e!s}"
			)

	frappe.db.commit()
