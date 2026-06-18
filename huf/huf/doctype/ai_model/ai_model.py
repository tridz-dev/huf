# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document



class AIModel(Document):
	def validate(self):
		"""Validate that both input and output prices are set when custom pricing is enabled."""
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
	modality = (filters or {}).get("modality")
	provider = (filters or {}).get("provider")

	if not modality:
		frappe.throw(_("Missing required filter: modality"))

	if modality not in {"Text", "Image", "Text-to-Speech", "Transcription", "Embeddings"}:
		frappe.throw(_("Invalid modality: {0}").format(modality))

	conditions = ["(model_name LIKE %(txt)s OR name LIKE %(txt)s)"]
	params = {"txt": f"%{txt}%", "modality": modality, "start": start, "page_len": page_len}

	conditions.append("IFNULL(modalities, '') = %(modality)s")

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
