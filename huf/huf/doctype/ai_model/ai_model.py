# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

MODEL_MODALITY_OPTIONS = {
	"Text",
	"Image",
	"Text-to-Speech",
	"Transcription",
	"Embeddings",
	"Vision",
	"OCR",
	"Speech-to-Speech",
}


class AIModel(Document):
	def validate(self):
		"""Validate modalities and that both input and output prices are set when custom pricing is enabled."""
		self._validate_modalities()

		if not self.get("use_custom_pricing"):
			return

		input_price = self.get("input_cost_per_1m_tokens")
		output_price = self.get("output_cost_per_1m_tokens")

		# If one is set but not the other, throw a clear validation error
		if (input_price is not None and input_price != 0) and (output_price is None or output_price == 0):
			frappe.throw(
				_("Custom pricing is enabled. Please also set 'Output Cost per 1M Tokens'.")
			)
		if (output_price is not None and output_price != 0) and (input_price is None or input_price == 0):
			frappe.throw(
				_("Custom pricing is enabled. Please also set 'Input Cost per 1M Tokens'.")
			)

	def _validate_modalities(self):
		"""Normalize and validate the comma-separated modalities value."""
		modalities = self.get("modalities") or ""
		if not modalities:
			return

		seen = set()
		items = []
		for m in modalities.split(","):
			item = m.strip()
			if not item or item in seen:
				continue
			seen.add(item)
			items.append(item)

		invalid = [m for m in items if m not in MODEL_MODALITY_OPTIONS]
		if invalid:
			frappe.throw(
				_(
					"Invalid modality value(s): {0}. Allowed values are: {1}."
				).format(", ".join(invalid), ", ".join(sorted(MODEL_MODALITY_OPTIONS)))
			)

		# Store as a normalized comma-separated string (no spaces so FIND_IN_SET matches cleanly)
		self.modalities = ",".join(items)

	def on_update(self):
		"""Invalidate Redis pricing cache so the next request picks up fresh data."""
		from huf.ai.cost_calculator import invalidate_model_pricing_cache

		invalidate_model_pricing_cache(self.name)



@frappe.whitelist()
def get_models_by_modality(doctype, txt, searchfield, start, page_len, filters):
	"""
	Link field query for AI Model with modality filtering.

	Supports Frappe link query signature.

	Expected filters:
	- modality (str): one of the configured modality options
	- provider (optional): AI Provider name (DocType link) to further restrict
	"""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}

	filters = filters or {}
	modality = filters.get("modality")
	provider = filters.get("provider")

	if not modality:
		frappe.throw(_("Missing required filter: modality"))

	if modality not in MODEL_MODALITY_OPTIONS:
		frappe.throw(_("Invalid modality: {0}").format(modality))

	conditions = ["(model_name LIKE %(txt)s OR name LIKE %(txt)s)"]
	params = {
		"txt": f"%{txt or ''}%",
		"modality": modality,
		"start": int(start or 0),
		"page_len": int(page_len or 20),
	}

	# Modalities are stored as a comma-separated list; use FIND_IN_SET for multi-select matching.
	# Strip spaces from the stored value so legacy or spaced modalities still match cleanly.
	conditions.append("FIND_IN_SET(%(modality)s, REPLACE(IFNULL(modalities, ''), ' ', '')) > 0")

	if provider:
		conditions.append("provider = %(provider)s")
		params["provider"] = provider

	return frappe.db.sql(
		f"""
		SELECT name, model_name
		FROM `tabAI Model`
		WHERE {" AND ".join(conditions)}
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		params,
	)
