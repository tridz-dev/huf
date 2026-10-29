"""Which document types a "When a document changes" trigger offers, and how they are named.

Pure functions over rows ``{name, module, custom}`` so the choice of what to show is testable without a bench. The
picker lists the things people think of as records (a ToDo, a Customer, a Sales Order, a table they made), leaves out
the system's own bookkeeping (permissions, tokens, logs, print settings, Huf's internals) and groups the rest:

* ``common``: the everyday records every site has (To-do, Note, Calendar event, User, File).
* ``yours``: tables someone created on this site.
* ``apps``: records that come with an installed app (Customer, Sales Order, Contact...).
"""

from __future__ import annotations

COMMON = {
	"ToDo": "To-do",
	"Note": "Note",
	"Event": "Calendar event",
	"User": "User",
	"File": "File",
	"Communication": "Email or message",
}

#: Modules that only hold the system's own plumbing. Their types are left out, except the ``COMMON`` ones.
SYSTEM_MODULES = frozenset(
	{"Core", "Desk", "Email", "Integrations", "Printing", "Website", "Workflow", "Automation", "Custom", "Huf", "Geo"}
)

#: Left out wherever they live (never something a flow should react to).
NEVER = frozenset({"DocPerm", "Custom DocPerm", "DocType", "DocField", "Patch Log", "Module Def", "Deleted Document"})
NEVER_PREFIXES = ("OAuth", "Personal Data", "Token ", "Email Queue", "Email Flag", "Integration Request", "Webhook Request")

GROUP_ORDER = {"common": 0, "yours": 1, "apps": 2}
GROUP_TITLE = {"common": "Everyday records", "yours": "Your tables", "apps": "From your apps"}


def classify(name: str, module: str | None, custom: bool = False) -> str | None:
	"""``common`` / ``yours`` / ``apps``, or None when the type is system plumbing that should not be offered."""
	if name in NEVER or name.startswith(NEVER_PREFIXES):
		return None
	if name in COMMON:
		return "common"
	if custom or (module == "Custom" and custom):
		return "yours"
	if module in SYSTEM_MODULES:
		# A table someone made lives in the "Custom" module but is flagged custom; anything else there is system.
		return None
	return "apps"


def friendly_label(name: str) -> str:
	return COMMON.get(name, name)


def build_catalog(rows) -> list[dict]:
	"""``rows`` of ``{name, module, custom}`` -> ``[{name, label, group, module}]`` ordered group, then label."""
	out: list[dict] = []
	for row in rows:
		name = row.get("name") if isinstance(row, dict) else None
		if not name:
			continue
		group = classify(name, row.get("module"), bool(row.get("custom")))
		if group is None:
			continue
		out.append({"name": name, "label": friendly_label(name), "group": group, "module": row.get("module") or ""})
	out.sort(key=lambda d: (GROUP_ORDER[d["group"]], d["label"].lower()))
	return out
