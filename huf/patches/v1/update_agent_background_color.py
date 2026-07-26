import frappe
import random

def execute():
    avatar_colors_hex = [
    "#6366F1",  # indigo-500
    "#2563EB",  # blue-600
    "#10B981",  # emerald-500
    "#14B8A6",  # teal-500
    "#8B5CF6",  # violet-500
    "#A855F7",  # purple-500
    "#F97316",  # orange-500
    "#F43F5E",  # rose-500
    "#475569",  # slate-600
    "#52525B",  # zinc-600
    ]

    agents = frappe.get_all("Agent", filters={"agent_color": None})
    for agent in agents:
        random_color = random.choice(avatar_colors_hex)
        frappe.db.set_value("Agent", agent.name, "agent_color", random_color)