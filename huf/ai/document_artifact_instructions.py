# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Prompt sections teaching the model how to author document artifacts and
use the export/redline/list tools built for them.

Split into two pieces with different injection rules, because they have
different capability requirements:

- DOCUMENT_ARTIFACT_INSTRUCTIONS (authoring): emitting an
  <artifact type="document"> tag requires NO tool - it is parsed
  automatically on message save, exactly like chart/mermaid/html
  artifacts. This is injected UNCONDITIONALLY whenever allow_chat is set,
  the same way CHART_ARTIFACT_INSTRUCTIONS and AI_ELEMENT_INSTRUCTIONS
  are (see their call site in huf.ai.agent_integration). Without this, an
  agent with no document tools linked has no way to know the artifact
  type exists at all, and falls back to whatever it knows from training -
  observed in practice as the model dumping a raw python-docx script
  instead of using the artifact pipeline.

- DOCUMENT_EXPORT_TOOL_INSTRUCTIONS (export/redline/list): these DO
  require the corresponding Agent Tool Function to be linked to the
  agent, so this section is gated behind agent_has_document_tools,
  mirroring how MEDIA_ELEMENT_INSTRUCTIONS is gated behind
  agent_has_media_tools - describing a tool the agent cannot call would
  just cause a hallucinated tool-call attempt.
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

When the user asks for a document, report, proposal, memo, or anything they
may want to download as a PDF or Word file - INCLUDING when they explicitly
say "make it a docx" or "give me a Word document" - use
`<artifact type="document">` with markdown content. Do NOT write a
python-docx script, a code snippet, or any other workaround: the platform
renders this artifact type, and (when available - see below) exposes tools
to export it to a real .docx or .pdf file. Writing code for the user to run
themselves is the WRONG answer whenever this artifact type is available -
it produces no actual file and asks the user to do the work you were asked
to do. A downloadable .docx is delivered by the export pipeline, not by
generating a python script.

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

### Multi-column layout

Wrap a region in `:::columns-2` / `:::columns-3` ... `:::` (own line, exact
match, no other content on the marker lines) to lay it out in real
newspaper-style columns in both the PDF and the DOCX export - not just a
visual CSS effect, a genuine multi-column DOCX section:

```
:::columns-2
## Left topic

Ordinary markdown works normally inside here - headings, paragraphs,
lists, tables.

## Right topic

More content, flows into the second column automatically.
:::
```

Content before and after the `:::columns-N` block stays in normal
single-column flow.

### What NOT to put in a document artifact

Never put a markdown code fence (```) inside a document artifact's content -
the same rule that applies to every other artifact type. Never put raw HTML
tags in it either; only the markdown syntax above is rendered - anything
else is stripped for safety before export.

### Downloading

If the user just asks to download the document you created as PDF or DOCX,
tell them the download buttons already shown on the artifact do this - you
do not need to do anything else; a working file is produced automatically
from the markdown content once the artifact is saved.
"""

DOCUMENT_EXPORT_TOOL_INSTRUCTIONS = """
### Exporting and redlining via tools - id sequencing matters

You also have `list_document_artifacts`, `export_artifact`, and
`redline_artifact` tools for cases where YOU (not the user clicking a
button) need to trigger an export or produce a marked-up revision - for
example, exporting a document from several turns ago, or applying suggested
edits as Word tracked changes rather than silently rewriting the document.

A document artifact's id is NOT known to you at the moment you emit its
`<artifact type="document">` tag - it is only assigned after that message
is saved. You cannot call `export_artifact` or `redline_artifact` on a
document you are creating in the CURRENT response.

To export or redline a document created earlier in the conversation (by you
or by a previous turn):
1. Call `list_document_artifacts(conversation_id)` first to find its id.
2. Call `export_artifact(artifact_id, format)` with `format` one of `"pdf"`,
   `"docx"`, `"html"` - returns a downloadable file URL.
3. To suggest edits as Word tracked changes, call
   `redline_artifact(artifact_id, edits, author)` with `edits` as a list of
   `{"find": "...", "replace": "..."}` objects. This produces a NEW derived
   DOCX with insertions/deletions marked - it does not modify the
   artifact's own content, so the original stays intact.
"""
