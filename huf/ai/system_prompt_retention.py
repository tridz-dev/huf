# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Opt-in persistence of the exact assembled system prompt an Agent Run received.

D15 in the analytics/observability audit: context_segments.py counts the token
*size* of the system prompt (segment_tokens.system) but never keeps its *text*,
so "what did this run actually see" is unanswerable once agent or skill config
changes. Persisting the full text unconditionally would be the wrong default:
unbounded storage growth, and a new PII surface, since the assembled prompt
includes memory-block and injected knowledge-base text that may carry user
data. Some deployments legitimately need the opposite of the default here --
legal/compliance obligations to retain the exact prompt a run saw -- so this
is a site operator's explicit choice, off unless turned on:

    bench set-config huf_retain_system_prompts_enabled true

When enabled, the exact text is written to a dedicated Agent Run Prompt
Snapshot doc rather than onto Agent Run itself, so a future retention/rotation
job (not built here) can purge old snapshots by captured_at without touching
the Agent Run table, and so the snapshot table can carry its own, tighter
permissions than Agent Run's.

Scope note: this is a system-wide switch, not a per-agent one, exactly as
requested. A per-agent override that further narrows this site-wide switch is
a natural follow-up once there is a field on the Agent doctype for it; it
would check both switches (site-wide AND per-agent), not replace this one.
"""

import frappe

SITE_CONFIG_KEY = "huf_retain_system_prompts_enabled"


def is_enabled() -> bool:
    return bool(frappe.conf.get(SITE_CONFIG_KEY))


def maybe_snapshot_system_prompt(run_name, agent_name, conversation_name, instructions):
    """Best-effort, opt-in only. Never raises -- a snapshot failure must never fail the run."""
    if not is_enabled() or not instructions:
        return
    try:
        frappe.get_doc({
            "doctype": "Agent Run Prompt Snapshot",
            "agent_run": run_name,
            "agent": agent_name,
            "conversation": conversation_name,
            "captured_at": frappe.utils.now_datetime(),
            "system_prompt": instructions,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="System Prompt Retention",
            message=f"Failed to snapshot system prompt for Agent Run {run_name}\n\n{frappe.get_traceback()}",
        )
