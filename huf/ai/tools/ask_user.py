"""
ask_user builder tool — structured question blocks for the hub chat.

The tool validates a question payload against the shared ask-user contract
(see .withkids hub-round3 tracker) and returns a fenced ``ask-user`` block
the agent must include verbatim in its reply. The frontend parses that block
out of the assistant content and renders an interactive card. Read-only —
no DB writes, no confirm phase.
"""

import json

import frappe
from frappe import _

from huf.ai.tools.builder import _as_bool, _require_builder_capability

ASK_USER_KINDS = ("yes_no", "single_choice", "multi_choice", "input", "textarea")

# Kinds that require a non-empty options list.
_CHOICE_KINDS = ("single_choice", "multi_choice")

# Curated lucide icon allowlist for option icons; anything else is dropped
# with a warning. The frontend falls back to CircleHelp when no icon is set.
ALLOWED_ICONS = (
	"Check",
	"X",
	"ThumbsUp",
	"ThumbsDown",
	"Car",
	"DollarSign",
	"Calendar",
	"User",
	"Users",
	"Settings",
	"Bot",
	"Workflow",
	"Database",
	"BookOpen",
	"Cpu",
	"Plus",
	"Send",
	"Sparkles",
	"Home",
	"LayoutDashboard",
	"MessageSquare",
)


def _parse_options(value):
	"""Accept a list or a JSON-encoded list (LLMs often stringify arguments)."""
	if value is None:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			frappe.throw(_("'options' must be a list or a JSON-encoded list."))
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("'options' must be a list or a JSON-encoded list."))
	return list(value)


def _clean_options(raw_options):
	"""Validate/normalize option dicts; drop invalid icons with a warning."""
	cleaned = []
	invalid_icons = []
	for raw in raw_options:
		if not isinstance(raw, dict):
			frappe.throw(_("Each option must be an object with id and label."))
		option_id = str(raw.get("id") or "").strip()
		label = str(raw.get("label") or "").strip()
		if not option_id or not label:
			frappe.throw(_("Each option needs a non-empty id and label."))
		option = {"id": option_id, "label": label}
		icon = raw.get("icon")
		if icon:
			if icon in ALLOWED_ICONS:
				option["icon"] = icon
			else:
				invalid_icons.append(icon)
		description = raw.get("description")
		if description:
			option["description"] = str(description)
		cleaned.append(option)
	return cleaned, invalid_icons


def ask_user(
	question: str,
	kind: str,
	options=None,
	allow_free_text: bool = True,
	suggested_answers=None,
	note: str | None = None,
) -> dict:
	"""Build a validated ask-user block for the hub chat to render.

	Read-only: returns a cleaned payload plus the fenced block to include
	verbatim in the assistant reply. kind must be one of
	yes_no|single_choice|multi_choice|input|textarea. Choice kinds require
	options as [{id, label, icon?, description?}]; icon names outside the
	curated lucide allowlist are dropped with a warning.
	"""
	_require_builder_capability()

	question = (question or "").strip()
	if not question:
		frappe.throw(_("'question' is required."))

	if kind not in ASK_USER_KINDS:
		frappe.throw(
			_("'kind' must be one of: {0}.").format(", ".join(ASK_USER_KINDS))
		)

	cleaned_options, invalid_icons = _clean_options(_parse_options(options))
	if kind in _CHOICE_KINDS and not cleaned_options:
		frappe.throw(_("kind '{0}' requires a non-empty options list.").format(kind))

	payload = {
		"question": question,
		"kind": kind,
		"options": cleaned_options,
		"allow_free_text": _as_bool(allow_free_text),
	}

	answers = _parse_options(suggested_answers)
	payload["suggested_answers"] = [str(answer) for answer in answers if answer]

	if note:
		payload["note"] = str(note)

	result = {
		"ask_user": payload,
		"block": f"```ask-user\n{json.dumps(payload, ensure_ascii=False)}\n```",
		"instruction": (
			"Include the 'block' value verbatim in your reply to the user, "
			"then stop and wait for their answer."
		),
	}

	if invalid_icons:
		result["warning"] = (
			"Dropped icons outside the allowlist: "
			+ ", ".join(sorted(set(invalid_icons)))
		)

	return result
