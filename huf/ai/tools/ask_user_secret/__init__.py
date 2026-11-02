"""Secret-kind questions of ``ask_user`` (masked fields, values stashed server-side, never sent to chat).

The shared helpers come from ``huf.ai.tools.ask_user``, imported lazily: that module imports this one.
"""

from frappe import _


def _normalize_secret_fields(raw_fields, index: int) -> list[dict]:
	"""Validate ``fields`` of a secret question: non-empty, unique ids, non-empty labels."""
	from huf.ai.tools import ask_user

	fields = ask_user._parse_json_list(raw_fields, f"questions[{index}].fields")
	if not fields:
		ask_user._usage_error(_("questions[{0}] with kind 'secret' needs at least one field.").format(index))
	if len(fields) > ask_user.MAX_SECRET_FIELDS:
		ask_user._usage_error(_("questions[{0}] has more than {1} secret fields.").format(index, ask_user.MAX_SECRET_FIELDS))
	cleaned, seen = [], set()
	for pos, raw in enumerate(fields):
		if not isinstance(raw, dict):
			ask_user._usage_error(_("questions[{0}].fields[{1}] must be an object with id and label.").format(index, pos))
		field_id = ask_user._safe_id(raw.get("id") or "")
		if not field_id:
			ask_user._usage_error(_("questions[{0}].fields[{1}] needs a non-empty id.").format(index, pos))
		if field_id in seen:
			ask_user._usage_error(_("questions[{0}].fields has duplicate id '{1}'.").format(index, field_id))
		seen.add(field_id)
		label = ask_user._cap_text(str(raw.get("label") or "").strip())
		if not label:
			ask_user._usage_error(_("questions[{0}].fields[{1}] needs a non-empty label.").format(index, pos))
		cleaned.append({"id": field_id, "label": label, "secret": True})
	return cleaned


def _normalize_secret_question(raw: dict, qid: str, text: str, index: int) -> dict:
	"""A ``kind: "secret"`` question: masked fields only, no options, no free text."""
	from huf.ai.tools import ask_user

	return {
		"id": qid,
		"text": text,
		"kind": ask_user._SECRET_KIND,
		"options": [],
		"allow_multiple": False,
		"allow_free_text": False,
		"fields": _normalize_secret_fields(raw.get("fields"), index),
		"purpose": ask_user._cap_text(str(raw.get("purpose") or "").strip() or text),
	}


def _secret_block_extras(question: dict) -> dict:
	"""Fields and purpose travel in the block only for secret questions."""
	from huf.ai.tools import ask_user

	if question["kind"] != ask_user._SECRET_KIND:
		return {}
	return {"fields": question["fields"], "purpose": question["purpose"]}
