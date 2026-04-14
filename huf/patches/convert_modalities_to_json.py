import frappe
import json


def execute():
	"""Normalize modalities field to a single string for AI Model records."""
	
	# Get all AI Models that have modalities
	models = frappe.db.get_all(
		"AI Model",
		filters={"modalities": ["!=", ""]},
		fields=["name", "modalities"]
	)
	
	updated_count = 0
	for model in models:
		try:
			modalities_str = model.get("modalities", "")
			if not modalities_str:
				continue

			modalities_value = None
			try:
				parsed = json.loads(modalities_str)
				if isinstance(parsed, list) and parsed:
					modalities_value = parsed[0]
				else:
					modalities_value = parsed
			except (json.JSONDecodeError, TypeError):
				modalities_value = modalities_str

			if isinstance(modalities_value, str):
				modalities_value = modalities_value.strip()
			elif isinstance(modalities_value, (list, tuple)) and modalities_value:
				modalities_value = str(modalities_value[0]).strip()
			else:
				modalities_value = None

			if modalities_value:
				frappe.db.set_value(
					"AI Model",
					model.name,
					"modalities",
					modalities_value,
					update_modified=False
				)
				updated_count += 1

		except Exception as e:
			frappe.log_error(f"Error normalizing modalities for {model.name}: {str(e)}")

	if updated_count > 0:
		frappe.db.commit()
		print(f"✅ Normalized modalities for {updated_count} AI models")