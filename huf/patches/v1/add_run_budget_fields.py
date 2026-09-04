"""Migration patch: Add run budget fields to Agent Settings.

This patch initializes the run-budget configuration fields on Agent Settings
with their defaults, and logs any existing agents whose max_turns exceed the
new ceiling so operators know which agents will be clamped at run time.
"""

import frappe


def execute():
    """Initialize run budget fields and log over-ceiling agents."""

    # Check if Agent Settings exists; create it if not
    if not frappe.db.exists("Agent Settings", "Agent Settings"):
        frappe.get_doc({
            "doctype": "Agent Settings",
            "name": "Agent Settings",
        }).insert(ignore_if_duplicate=True)

    # Set default values for budget fields if not already set
    defaults = {
        "max_turns_ceiling": 20,
        "max_depth": 3,
        "deadline_seconds": 900,
        "spend_cap_usd": 0,
    }

    for field_name, default_value in defaults.items():
        current_value = frappe.db.get_single_value("Agent Settings", field_name)
        if current_value is None:
            frappe.db.set_single_value("Agent Settings", field_name, default_value)

    # Log summary
    ceiling = frappe.db.get_single_value("Agent Settings", "max_turns_ceiling") or 20
    max_depth = frappe.db.get_single_value("Agent Settings", "max_depth") or 3
    deadline = frappe.db.get_single_value("Agent Settings", "deadline_seconds") or 900
    spend_cap = frappe.db.get_single_value("Agent Settings", "spend_cap_usd") or 0

    frappe.logger("huf").info(
        f"Run budget fields initialized. Site-wide max_turns_ceiling: {ceiling}, "
        f"max_depth: {max_depth}, deadline_seconds: {deadline}, spend_cap_usd: {spend_cap}"
    )

    # Query existing agents and log any whose max_turns exceed the ceiling
    over_ceiling_agents = frappe.db.get_list(
        "Agent",
        filters=[["max_turns", ">", ceiling]],
        fields=["name", "max_turns"],
        limit_page_length=None,
    )

    if over_ceiling_agents:
        agent_list = ", ".join([f"{a['name']} (max_turns={a['max_turns']})" for a in over_ceiling_agents])
        frappe.logger("huf").warning(
            f"The following agents have max_turns exceeding the ceiling ({ceiling}) "
            f"and will be clamped at run time: {agent_list}"
        )
