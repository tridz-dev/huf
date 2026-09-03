import frappe


def execute():
	"""ST-R3.1b: Flip is_private=1 for all generated_image/audio files and rewrite stored URLs.

	For every File doc where:
	- attached_to_doctype == "Agent Message"
	- attached_to_field in ("generated_image", "generated_audio")
	- is_private == 0

	This patch:
	1. Sets is_private=1 on the File doc
	2. Rewrites the Agent Message's generated_image or generated_audio field from /files/<name> to /private/files/<name>

	This ensures all existing generated media files are marked private and their URLs updated to
	the private path, matching the new save_file behavior (ST-R3.1) which writes with is_private=True
	and /private/files/... fallback URLs.
	"""

	# Find all public media files linked to Agent Messages
	files = frappe.db.get_list(
		"File",
		filters={
			"attached_to_doctype": "Agent Message",
			"attached_to_field": ["in", ["generated_image", "generated_audio"]],
			"is_private": 0,
		},
		fields=["name", "file_name", "attached_to_name", "attached_to_field"],
		limit_page_length=None,  # Get all matching files
	)

	if not files:
		return

	frappe.msgprint(f"Privatizing {len(files)} generated media files...")

	for file_doc in files:
		file_name = file_doc["name"]
		attached_to_name = file_doc["attached_to_name"]
		attached_to_field = file_doc["attached_to_field"]

		# Set the File doc to private
		frappe.db.set_value("File", file_name, "is_private", 1)

		# Rewrite the Agent Message's URL field from /files/... to /private/files/...
		message_doc = frappe.get_doc("Agent Message", attached_to_name)
		current_url = getattr(message_doc, attached_to_field, None)

		if current_url and current_url.startswith("/files/"):
			new_url = current_url.replace("/files/", "/private/files/", 1)
			frappe.db.set_value("Agent Message", attached_to_name, attached_to_field, new_url)

	frappe.msgprint(f"Successfully privatized {len(files)} generated media files")
