# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AIModel(Document):
	pass


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
