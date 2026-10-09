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

from huf.ai.tools.builder import _as_bool

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
	if len(raw_options) > MAX_OPTIONS:
		_usage_error(_("at most {0} options per question.").format(MAX_OPTIONS))
	cleaned = []
	invalid_icons = []
	for raw in raw_options:
		if not isinstance(raw, dict):
			frappe.throw(_("Each option must be an object with id and label."))
		option_id = str(raw.get("id") or "").strip()
		label = _cap_text(str(raw.get("label") or "").strip())
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
			option["description"] = _cap_text(description)
		cleaned.append(option)
	return cleaned, invalid_icons


MAX_QUESTIONS = 10
MAX_OPTIONS = 12
# Upper bound for any single free-text field (question text, option label, title, ...).
MAX_TEXT_LENGTH = 500


def _cap_text(value, limit: int = MAX_TEXT_LENGTH) -> str:
	"""Return ``value`` as a string, truncated with an ellipsis to ``limit`` characters."""
	text = str(value)
	if len(text) <= limit:
		return text
	return text[: limit - 1].rstrip() + "…"

ASK_USER_EXAMPLE = {
	"title": "Project setup",
	"questions": [
		{
			"id": "project_type",
			"text": "What kind of project is this?",
			"options": ["Web app", "Mobile app", "Data pipeline"],
			"allow_free_text": True,
		},
		{
			"id": "features",
			"text": "Which features do you need?",
			"options": ["Auth", "Payments", "Analytics"],
			"allow_multiple": True,
		},
		{"id": "deadline", "text": "When is the deadline?"},
	],
}

ASK_USER_EXPECTED_SHAPE = (
	"{questions: [{id, text, options?: [string | {id, label, description?}], "
	"allow_multiple?: bool, allow_free_text?: bool, placeholder?: string}], title?: string}"
)

ASK_USER_DESCRIPTION = (
	"Ask the user one or more questions through a native question card in the chat "
	"(choices as buttons, free text as an input). The user's answers come back as their "
	"next message. ALWAYS pass a non-empty 'questions' array — never call this with empty "
	"arguments. Each question: {id, text, options?, allow_multiple?, allow_free_text?, "
	"placeholder?}; omit options for a free-text question. Example: "
	+ json.dumps(ASK_USER_EXAMPLE, ensure_ascii=False)
	+ ". After calling it, write at most one short sentence and STOP to wait for the "
	"answers. Use this tool whenever you need to ask the user questions — NEVER build a "
	"questionnaire, form, or wizard as a React/JSX/HTML artifact instead."
)

_OPTION_SCHEMA = {
	"type": "object",
	"properties": {
		"id": {"type": "string", "description": "Stable option id, e.g. 'web'"},
		"label": {"type": "string", "description": "Text shown on the option button"},
		"description": {"type": "string", "description": "Optional one-line hint"},
	},
	"required": ["label"],
}

ASK_USER_PARAMS_SCHEMA = {
	"type": "object",
	"properties": {
		"title": {"type": "string", "description": "Optional heading for the question card"},
		"questions": {
			"type": "array",
			"minItems": 1,
			"maxItems": MAX_QUESTIONS,
			"description": "The questions to ask (1-10). Required and must not be empty.",
			"items": {
				"type": "object",
				"properties": {
					"id": {"type": "string", "description": "Short unique id, e.g. 'deadline'"},
					"text": {"type": "string", "description": "The question shown to the user"},
					"options": {
						"type": "array",
						"description": "Choices; omit for a free-text question",
						"items": _OPTION_SCHEMA,
					},
					"allow_multiple": {
						"type": "boolean",
						"description": "Let the user pick more than one option",
					},
					"allow_free_text": {
						"type": "boolean",
						"description": "Also accept a typed answer besides the options (default true)",
					},
					"placeholder": {"type": "string", "description": "Placeholder for the text input"},
					"kind": {
						"type": "string",
						"enum": list(ASK_USER_KINDS),
						"description": "Optional; inferred from options/allow_multiple when omitted",
					},
				},
				"required": ["id", "text"],
			},
		},
	},
	"required": ["questions"],
}


def _usage_error(problem: str):
	"""Throw a validation error that tells the model exactly how to retry."""
	frappe.throw(
		_("ask_user: {0} Expected arguments: {1}. Example: {2}").format(
			problem, ASK_USER_EXPECTED_SHAPE, json.dumps(ASK_USER_EXAMPLE, ensure_ascii=False)
		)
	)


def _slug(value: str, fallback: str) -> str:
	slug = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")[:40]
	return slug or fallback


_ID_MAX = 64
_IGNORED_MAX_NAMES = 10
_IGNORED_NAME_MAX = 40


def _safe_token(value, limit: int) -> str:
	"""Reduce untrusted text to [A-Za-z0-9_.-], capped at ``limit`` characters."""
	return "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "_.-")) else "_" for ch in str(value))[:limit]


def _safe_id(value) -> str:
	return _safe_token(str(value).strip(), _ID_MAX)


def _parse_json_list(value, fieldname: str) -> list:
	if value is None or value == "":
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			_usage_error(_("'{0}' must be a list.").format(fieldname))
	if isinstance(value, dict):
		value = [value]
	if not isinstance(value, (list, tuple)):
		_usage_error(_("'{0}' must be a list.").format(fieldname))
	return list(value)


def _normalize_question_options(raw_options, index: int):
	if len(raw_options) > MAX_OPTIONS:
		_usage_error(_("questions[{0}] has more than {1} options.").format(index, MAX_OPTIONS))
	options, invalid_icons, seen = [], [], set()
	for pos, raw in enumerate(raw_options):
		if isinstance(raw, str):
			raw = {"label": raw}
		if not isinstance(raw, dict):
			_usage_error(_("questions[{0}].options[{1}] must be a string or {{id, label}}.").format(index, pos))
		label = str(raw.get("label") or raw.get("text") or "").strip()
		if not label:
			_usage_error(_("questions[{0}].options[{1}] needs a non-empty label.").format(index, pos))
		label = _cap_text(label)
		option_id = _safe_id(raw.get("id") or "") or _slug(label, f"opt_{pos + 1}")
		while option_id in seen:
			option_id = f"{option_id}_{pos + 1}"
		seen.add(option_id)
		option = {"id": option_id, "label": label}
		icon = raw.get("icon")
		if icon:
			if icon in ALLOWED_ICONS:
				option["icon"] = icon
			else:
				invalid_icons.append(icon)
		if raw.get("description"):
			option["description"] = _cap_text(raw["description"])
		options.append(option)
	return options, invalid_icons


def normalize_questions(questions) -> tuple[list[dict], list[str]]:
	"""Validate the ``questions`` array into the canonical question shape.

	Each result: {id, text, kind, options, allow_multiple, allow_free_text, placeholder?}.
	``kind`` keeps the legacy hub vocabulary (single_choice/multi_choice/input/yes_no/textarea).
	"""
	raw_list = _parse_json_list(questions, "questions")
	if not raw_list:
		_usage_error(_("'questions' is required and must contain at least one question."))
	if len(raw_list) > MAX_QUESTIONS:
		_usage_error(_("at most {0} questions per call.").format(MAX_QUESTIONS))

	cleaned, invalid_icons, seen = [], [], set()
	for index, raw in enumerate(raw_list):
		if isinstance(raw, str):
			raw = {"text": raw}
		if not isinstance(raw, dict):
			_usage_error(_("questions[{0}] must be an object.").format(index))
		text = str(raw.get("text") or raw.get("question") or raw.get("label") or "").strip()
		if not text:
			_usage_error(_("questions[{0}].text is required.").format(index))
		text = _cap_text(text)
		qid = _safe_id(raw.get("id") or "") or f"q{index + 1}"
		while qid in seen:
			qid = f"{qid}_{index + 1}"
		seen.add(qid)

		options, bad_icons = _normalize_question_options(
			_parse_json_list(raw.get("options"), f"questions[{index}].options"), index
		)
		invalid_icons.extend(bad_icons)
		kind = raw.get("kind")
		allow_multiple = _as_bool(raw.get("allow_multiple", False)) or kind == "multi_choice"
		if kind == "yes_no" and not options:
			options = [{"id": "yes", "label": _("Yes")}, {"id": "no", "label": _("No")}]
		if kind not in ASK_USER_KINDS:
			kind = None
		if kind in _CHOICE_KINDS and not options:
			kind = None
		if kind == "single_choice" and allow_multiple and options:
			# allow_multiple wins: a single_choice block would carry no multi flag.
			kind = "multi_choice"
		if not kind:
			kind = ("multi_choice" if allow_multiple else "single_choice") if options else "input"

		question = {
			"id": qid,
			"text": text,
			"kind": kind,
			"options": options,
			"allow_multiple": allow_multiple and bool(options),
			"allow_free_text": _as_bool(raw.get("allow_free_text", True)) or not options,
		}
		if raw.get("placeholder"):
			question["placeholder"] = _cap_text(raw["placeholder"])
		cleaned.append(question)
	return cleaned, invalid_icons


def ask_user(
	questions=None,
	title: str | None = None,
	question: str | None = None,
	kind: str | None = None,
	options=None,
	allow_free_text: bool = True,
	suggested_answers=None,
	note: str | None = None,
	**_ignored,
) -> dict:
	"""Validate questions for the chat's native question card.

	Preferred form: ``questions=[{id, text, options?, allow_multiple?, allow_free_text?}]``.
	The legacy single-question form (``question`` + ``kind``) is still accepted for the hub.
	Every validation failure raises with the expected shape and an example so the model
	can correct its call (the tool wrapper returns the message as ``{"error": ...}``).
	"""
	# No builder-role gate: this only validates questions for the user's own chat card.
	ignored = _report_ignored_arguments(_ignored)

	if questions in (None, "", [], {}) and question is None and kind is None:
		_usage_error(_("called without questions."))

	if questions in (None, "", [], {}):
		result = _legacy_single(question, kind, options, allow_free_text, suggested_answers, note)
		return _attach_ignored(result, ignored)

	cleaned, invalid_icons = normalize_questions(questions)
	payload = {"questions": cleaned}
	if title:
		payload["title"] = _cap_text(str(title).strip())
	if note:
		payload["note"] = _cap_text(note)

	blocks = [
		"```ask-user\n"
		+ json.dumps(
			{
				"id": q["id"],
				"question": q["text"],
				"kind": q["kind"],
				"options": q["options"],
				"allow_free_text": q["allow_free_text"],
			},
			ensure_ascii=False,
		)
		+ "\n```"
		for q in cleaned
	]
	result = {
		"ask_user": payload,
		"block": "\n\n".join(blocks),
		"instruction": (
			"The question card is now shown to the user. Do not repeat the questions or "
			"build a form/artifact; stop and wait for the user's answers in their next message."
		),
	}
	if invalid_icons:
		result["warning"] = "Dropped icons outside the allowlist: " + ", ".join(sorted(set(invalid_icons)))
	return _attach_ignored(result, ignored)


ask_user.tool_params_schema = ASK_USER_PARAMS_SCHEMA


def _report_ignored_arguments(extra: dict) -> list[str]:
	"""Log the names (never the values) of unrecognised arguments; return them sorted."""
	names = sorted({_safe_token(key, _IGNORED_NAME_MAX) for key in extra})
	ignored = names[:_IGNORED_MAX_NAMES]
	if len(names) > _IGNORED_MAX_NAMES:
		ignored.append(f"... (+{len(names) - _IGNORED_MAX_NAMES} more)")
	if ignored:
		frappe.logger("huf").warning(f"ask_user ignored unrecognised arguments: {', '.join(ignored)}")
	return ignored


def _attach_ignored(result: dict, ignored: list[str]) -> dict:
	"""Surface ignored argument names to the model so typos are visible; only when present."""
	if ignored:
		result["ignored_arguments"] = ignored
	return result


def _legacy_single(question, kind, options, allow_free_text, suggested_answers, note) -> dict:
	"""The original one-question contract (hub chat). Shape kept byte-compatible."""
	question = _cap_text((question or "").strip())
	if not question:
		_usage_error(_("'question' is required."))

	if kind not in ASK_USER_KINDS:
		_usage_error(_("'kind' must be one of: {0}.").format(", ".join(ASK_USER_KINDS)))

	cleaned_options, invalid_icons = _clean_options(_parse_options(options))
	if kind in _CHOICE_KINDS and not cleaned_options:
		_usage_error(_("kind '{0}' requires a non-empty options list.").format(kind))

	payload = {
		"question": question,
		"kind": kind,
		"options": cleaned_options,
		"allow_free_text": _as_bool(allow_free_text),
	}

	answers = _parse_options(suggested_answers)
	payload["suggested_answers"] = [str(answer) for answer in answers if answer]

	if note:
		payload["note"] = _cap_text(note)

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
