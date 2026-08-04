# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Prompt section teaching the model how to author document artifacts and use
the export/redline/list tools built for them.

Injected conditionally, the same way MEDIA_ELEMENT_INSTRUCTIONS is (see
huf.ai.artifact_instructions.agent_has_media_tools and its call site in
huf.ai.agent_integration): only when the acting agent actually has the
document tools available, so an agent without them never pays the token
cost of instructions it cannot act on.
"""

import re

import frappe

# Tool names that mark an agent as document-capable. Matches the exact
# tool_name values registered in huf.ai.tools._registry.DOCUMENT_ARTIFACT_TOOLS.
DOCUMENT_TOOL_NAME = re.compile(r"export_artifact|redline_artifact|list_document_artifacts", re.IGNORECASE)


def agent_has_document_tools(agent_doc) -> bool:
	"""True when the agent can export/redline document artifacts, so
	DOCUMENT_ARTIFACT_INSTRUCTIONS apply.

	Checks native Agent Tool Function names, mirroring
	huf.ai.artifact_instructions.agent_has_media_tools exactly. Any failure
	degrades to False (section skipped) - prompt assembly must never break a
	run.
	"""
	try:
		for row in agent_doc.get("agent_tool") or []:
			tool_name = frappe.db.get_value("Agent Tool Function", row.tool, "tool_name") or row.tool
			if DOCUMENT_TOOL_NAME.search(tool_name):
				return True
	except Exception:
		frappe.log_error("agent_has_document_tools failed", "Document Artifact Instructions")

	return False


DOCUMENT_ARTIFACT_INSTRUCTIONS = """
## Document Artifacts (PDF/DOCX export)

`<artifact type="document">` content is treated as markdown source that can
be exported to a real downloadable PDF or DOCX file. Use this artifact type
for reports, proposals, memos, or any content the user may want to download
or print - not for short answers that belong in your regular reply.

### Supported markdown

- Headings: `#` through `######`
- Paragraphs, **bold**, *italic*
- Tables: standard `| A | B |` / `|---|---|` syntax
- Blockquotes: `> quoted text`
- Bulleted lists (`- item`) and numbered lists (`1. item`)
- Links and images

### Alignment and indent

Attach a class to the line IMMEDIATELY above it, with NO blank line in
between, or the marker is dropped as literal text instead of being applied:

```
Right aligned text.
{: .text-right}

Indented text.
{: .indent-2}
```

Alignment classes: `.text-left`, `.text-center`, `.text-right`.
Indent classes: `.indent-1`, `.indent-2`, `.indent-3` (increasing depth).

### What NOT to put in a document artifact

Never put a markdown code fence (```) inside a document artifact's content -
the same rule that applies to every other artifact type. Never put raw HTML
tags in it either; only the markdown syntax above is rendered - anything
else is stripped for safety before export.

### Exporting and redlining - id sequencing matters

A document artifact's id is NOT known to you at the moment you emit its
`<artifact type="document">` tag - it is only assigned after that message
is saved. You cannot call `export_artifact` or `redline_artifact` on a
document you are creating in the CURRENT response.

To export or redline a document created earlier in the conversation (by you
or by a previous turn):
1. Call `list_document_artifacts(conversation_id)` first to find its id.
2. Call `export_artifact(artifact_id, format)` with `format` one of `"pdf"`,
   `"docx"`, `"html"` - returns a downloadable file URL.
3. To suggest edits as Word tracked changes rather than silently rewriting
   the document, call `redline_artifact(artifact_id, edits, author)` with
   `edits` as a list of `{"find": "...", "replace": "..."}` objects. This
   produces a NEW derived DOCX with insertions/deletions marked - it does
   not modify the artifact's own content, so the original stays intact.

If the user just asks to "download this as PDF" right after you created the
document, tell them the download buttons on the artifact itself already do
this - you do not need to call a tool for that; the tools above are for
when the MODEL needs to trigger an export or produce a redline, not for a
user clicking a button that already exists in the UI.
"""
