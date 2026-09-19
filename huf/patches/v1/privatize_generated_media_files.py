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

	IMPORTANT: the File doc's ``is_private`` flag must be flipped via a real Document
	save (``file_obj.save()``), not ``frappe.db.set_value``. Frappe's own
	``File.validate()`` only physically moves the underlying bytes from
	``public/files`` to ``private/files`` (``File.handle_is_private_changed``,
	triggered on ``has_value_changed("is_private")``) when the value is changed
	through the controller. A raw ``frappe.db.set_value`` write flips the DB column
	without moving the file, so the old public URL keeps serving the file (verified
	live: returns 200, not 404, after the naive patch runs) even though the DB now
	says ``is_private=1``.
	"""

	# Find all public media files linked to Agent Messages
	files = frappe.db.get_list(
		"File",
		filters={
			"attached_to_doctype": "Agent Message",
			"attached_to_field": ["in", ["generated_image", "generated_audio"]],
			"is_private": 0,
		},
		fields=["name", "attached_to_name", "attached_to_field"],
		limit_page_length=None,  # Get all matching files
	)

	if not files:
		return

	frappe.msgprint(f"Privatizing {len(files)} generated media files...")

	privatized = 0
	for file_doc in files:
		file_name = file_doc["name"]
		attached_to_name = file_doc["attached_to_name"]
		attached_to_field = file_doc["attached_to_field"]

		# Flip via a real Document save so File.validate() ->
		# handle_is_private_changed() actually moves the bytes on disk and
		# rewrites File.file_url, not just the DB column.
		try:
			file_obj = frappe.get_doc("File", file_name)
			file_obj.is_private = 1
			file_obj.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="privatize_generated_media_files: failed to privatize File",
				message=frappe.get_traceback(),
			)
			continue

		# Rewrite the Agent Message's URL field to match the File doc's own
		# (now-updated) file_url, rather than assuming the /files/ -> /private/files/
		# string substitution always matches what handle_is_private_changed produced.
		new_url = file_obj.file_url
		if new_url:
			frappe.db.set_value("Agent Message", attached_to_name, attached_to_field, new_url)

		privatized += 1

	frappe.msgprint(f"Successfully privatized {privatized} of {len(files)} generated media files")
