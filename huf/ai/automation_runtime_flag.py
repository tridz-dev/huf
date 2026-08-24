# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""Shared site-config flag gating live Automation runtime code paths.

Stage 2 hard-cuts ``hooks.py``'s scheduler/doc-event registrations onto the
new ``automation_scheduler.py`` / ``automation_hooks.py`` entrypoints, but
keeps a one-line rollback available without a code revert: setting
``automation_trigger_runtime`` to ``"legacy"`` in ``site_config.json`` makes
every new entrypoint that checks this flag act as disabled and hands the work
back to the legacy ``agent_scheduler.py`` / ``agent_hooks.py`` entrypoints.

Both sides check this flag, with opposite polarity: the new entrypoints
return early when the mode is *not* ``"new"``, the legacy ones return early
when it *is*. ``hooks.py`` registers both, so exactly one of each pair ever
executes. The default is ``"new"``, which means the legacy scheduler and doc
hooks are inert on any site that has not explicitly opted into ``"legacy"``
-- tests that exercise them must patch ``automation_runtime_is_new`` rather
than only the calling module's ``frappe``, since this module holds its own
``frappe`` reference.

Webhook and App Event trigger types have no legacy counterpart (confirmed
by grep across the whole ``huf/`` tree -- see
``Tracks/safwan-erooth.ChatSidebarTriggerStage2/CONTEXT.md``), so for those
two "legacy" simply means "disabled" rather than "fall back to an old path".
"""

from __future__ import annotations

import frappe

_SITE_CONFIG_KEY = "automation_trigger_runtime"
_VALID_VALUES = ("legacy", "new")


def automation_runtime_mode() -> str:
	"""Return the configured mode: "legacy" or "new" (default "new" if unset or invalid)."""
	value = frappe.conf.get(_SITE_CONFIG_KEY)
	if value not in _VALID_VALUES:
		return "new"
	return value


def automation_runtime_is_new() -> bool:
	"""True unless site config explicitly opts into "legacy" mode."""
	return automation_runtime_mode() == "new"
