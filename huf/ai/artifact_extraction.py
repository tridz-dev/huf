# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Extract AI-generated artifact blocks from an Agent Message's content and
persist them as ``Artifact`` rows.

Ports the three client-side parsers (``artifactParser.ts``, ``webPreviewParser.ts``,
``jsxPreviewParser.ts``) to Python so artifacts get a stable, server-owned
identity instead of only existing as a browser-side parse of the message
content. Identity is ``(message, message_index)`` — see
``huf.huf.doctype.artifact.artifact`` for the rationale.
"""

import re

import frappe

#: <artifact type="code" language="python" title="Hello">content</artifact>
#: Also accepts the legacy "antArtifact" tag name.
ARTIFACT_REGEX = re.compile(
	r"<(?:artifact|antArtifact)\s+([^>]*)>([\s\S]*?)</(?:artifact|antArtifact)>",
	re.IGNORECASE,
)

#: <web-preview url="..." title="..." /> or <web-preview url="..." title="..."></web-preview>
WEB_PREVIEW_REGEX = re.compile(
	r"<web-preview\s+([^>]*?)\s*(?:/>|></web-preview>)",
	re.IGNORECASE,
)

#: <jsx-preview title="...">body</jsx-preview> or <jsx-preview jsx="..." title="..." />
JSX_PREVIEW_REGEX = re.compile(
	r"<jsx-preview\s*([^>]*?)>(?:([\s\S]*?)</jsx-preview>|(?:/>))",
	re.IGNORECASE,
)

ATTR_REGEX = re.compile(r"(\w+)=[\"']([^\"']*)[\"']")

#: Must mirror the Select options on Artifact.artifact_type in artifact.json.
VALID_ARTIFACT_TYPES = {
	"code",
	"document",
	"markdown",
	"html",
	"svg",
	"mermaid",
	"chart",
	"jsx",
	"video",
	"image",
	"web-preview",
	"text",
}

#: Agent Message roles that represent an assistant/agent turn, as opposed to
#: "user", "tool" or "system".
ASSISTANT_ROLES = {"agent"}


def _parse_attrs(raw_attrs: str) -> dict:
	"""Parse a tag's attribute string (e.g. ``type="code" title="Hi"``) into a dict."""
	return dict(ATTR_REGEX.findall(raw_attrs or ""))


def _normalize_artifact_type(raw_type: str) -> str:
	"""Map a raw ``type=`` attribute value onto one of the Select options.

	Unrecognised values (including a missing attribute other than the
	"code" default used by the ``<artifact>`` tag) fall back to "text".
	"""
	candidate = (raw_type or "").strip().lower()
	if candidate in VALID_ARTIFACT_TYPES:
		return candidate
	return "text"


def _parse_artifact_tags(content: str) -> list[dict]:
	blocks = []
	for match in ARTIFACT_REGEX.finditer(content):
		attrs = _parse_attrs(match.group(1))
		body = (match.group(2) or "").strip()
		if not body:
			continue
		raw_type = attrs.get("type") or "code"
		blocks.append(
			{
				"start": match.start(),
				"artifact_type": _normalize_artifact_type(raw_type),
				"title": attrs.get("title") or "",
				"language": attrs.get("language") or "",
				"content": body,
			}
		)
	return blocks


def _parse_web_preview_tags(content: str) -> list[dict]:
	blocks = []
	for match in WEB_PREVIEW_REGEX.finditer(content):
		attrs = _parse_attrs(match.group(1))
		url = attrs.get("url") or ""
		if not url:
			continue
		blocks.append(
			{
				"start": match.start(),
				"artifact_type": "web-preview",
				"title": attrs.get("title") or "",
				"language": "",
				"content": url,
			}
		)
	return blocks


def _parse_jsx_preview_tags(content: str) -> list[dict]:
	blocks = []
	for match in JSX_PREVIEW_REGEX.finditer(content):
		attrs = _parse_attrs(match.group(1))
		body = match.group(2)
		# The body form is primary; only fall back to the jsx= attribute when
		# there is no closing-tag body (i.e. the self-closing form).
		jsx_content = (body if body is not None else attrs.get("jsx") or "").strip()
		if not jsx_content:
			continue
		blocks.append(
			{
				"start": match.start(),
				"artifact_type": "jsx",
				"title": attrs.get("title") or "",
				"language": "",
				"content": jsx_content,
			}
		)
	return blocks


def parse_artifacts(content: str) -> list[dict]:
	"""Extract all artifact-like blocks from ``content``, in document order.

	Recognises three tag families: ``<artifact>``/``<antArtifact>``,
	``<web-preview>`` and ``<jsx-preview>``. Each returned dict has keys
	``artifact_type``, ``title``, ``language`` and ``content``. Blocks with
	empty content are skipped.
	"""
	if not content:
		return []

	blocks = (
		_parse_artifact_tags(content)
		+ _parse_web_preview_tags(content)
		+ _parse_jsx_preview_tags(content)
	)
	blocks.sort(key=lambda block: block["start"])

	return [
		{
			"artifact_type": block["artifact_type"],
			"title": block["title"],
			"language": block["language"],
			"content": block["content"],
		}
		for block in blocks
	]


def sync_message_artifacts(message_doc) -> int:
	"""Idempotently sync ``Artifact`` rows for one Agent Message.

	Parses ``message_doc.content`` and reconciles it against the existing
	Artifact rows for this message, keyed by ``(message, message_index)``:
	matching rows are updated in place, new ordinals are inserted, and
	ordinals beyond the newly parsed count are deleted so re-runs and edits
	never leave orphaned rows behind.

	Returns the number of Artifact rows that exist for the message after
	the sync. Messages whose role is not an assistant/agent role are
	skipped and return 0 without touching the database.
	"""
	if message_doc.role not in ASSISTANT_ROLES:
		return 0

	parsed_blocks = parse_artifacts(message_doc.content)

	existing_rows = frappe.get_all(
		"Artifact",
		filters={"message": message_doc.name},
		fields=[
			"name",
			"message_index",
			"title",
			"language",
			"artifact_type",
			"content",
			"conversation",
			"agent",
		],
		order_by="message_index asc",
	)
	existing_by_index = {row.message_index: row for row in existing_rows}

	for index, block in enumerate(parsed_blocks):
		existing_row = existing_by_index.get(index)
		if existing_row:
			_update_artifact_if_changed(existing_row, block, message_doc)
		else:
			_insert_artifact(index, block, message_doc)

	surplus_indices = [index for index in existing_by_index if index >= len(parsed_blocks)]
	for index in surplus_indices:
		frappe.delete_doc(
			"Artifact",
			existing_by_index[index].name,
			ignore_permissions=True,
			force=True,
		)

	return len(parsed_blocks)


def _update_artifact_if_changed(existing_row, block: dict, message_doc) -> None:
	changed_fields = {}
	for field in ("title", "language", "artifact_type", "content"):
		if existing_row.get(field) != block[field]:
			changed_fields[field] = block[field]

	if existing_row.get("conversation") != message_doc.conversation:
		changed_fields["conversation"] = message_doc.conversation
	if existing_row.get("agent") != message_doc.agent:
		changed_fields["agent"] = message_doc.agent

	if not changed_fields:
		return

	artifact_doc = frappe.get_doc("Artifact", existing_row.name)
	for field, value in changed_fields.items():
		artifact_doc.set(field, value)
	artifact_doc.save(ignore_permissions=True)


def _insert_artifact(index: int, block: dict, message_doc) -> None:
	artifact_doc = frappe.get_doc(
		{
			"doctype": "Artifact",
			"conversation": message_doc.conversation,
			"message": message_doc.name,
			"agent": message_doc.agent,
			"message_index": index,
			"artifact_type": block["artifact_type"],
			"title": block["title"],
			"language": block["language"],
			"content": block["content"],
		}
	)
	artifact_doc.insert(ignore_permissions=True)


def on_agent_message_change(doc, method=None):
	"""Hook entrypoint: sync artifacts for an Agent Message after insert/update.

	Must never raise — a parsing bug here must not block the Agent Message
	itself from saving.
	"""
	try:
		sync_message_artifacts(doc)
	except Exception:
		frappe.log_error(
			title="Artifact extraction failed",
			message=frappe.get_traceback(),
		)
