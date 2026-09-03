import frappe


def execute():
    """
    Audit patch: log count of existing agents with run_immediately=1.

    After ST-08.1 (which flips the default to 0), existing agents keep their
    configured setting and continue to run immediately. This patch logs an
    audit message to help operators understand the migration state.

    Rationale: do not retroactively change agent settings — let operators
    manage migrations per-site. Log a count for visibility.
    """
    count = frappe.db.count("Agent", filters={"run_immediately": 1})
    if count > 0:
        agents = frappe.db.get_list(
            "Agent",
            filters={"run_immediately": 1},
            fields=["name"],
            limit_page_length=100
        )
        agent_names = [a["name"] for a in agents]
        message = (
            f"{count} agents have run_immediately=1 and will continue to run "
            f"planning/execution inline (not queued). "
            f"New agents default to queued (run_immediately=0) for stability. "
            f"First 100 agents: {', '.join(agent_names[:100])}"
        )
        frappe.logger().warning(message)
    else:
        frappe.logger().info(
            "No agents with run_immediately=1 found. All agents will use the "
            "new default (queued, run_immediately=0)."
        )
