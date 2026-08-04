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
may want to download as a PDF or Word file - INCLUDING when they say "make
it a docx" - use `<artifact type="document">`. Never write a python-docx
script or any other code workaround: the platform renders this type and
exports it to a real .pdf/.docx. Emitting a script produces no file and
hands the work back to the user.

Content is markdown by default: headings, **bold**, *italic*, tables,
blockquotes, lists, links and images all work. Never put a markdown code
fence (```) inside a document artifact.

### Alignment, indent, columns

Attach a class to the line IMMEDIATELY above it, with NO blank line between,
or the marker is dropped as literal text:

```
Right aligned text.
{: .text-right}
```

Classes: `.text-left`, `.text-center`, `.text-right`, `.indent-1` through
`.indent-3`.

Wrap a region in `:::columns-2` (or `-3`) ... `:::`, each marker alone on
its own line, for genuine newspaper columns in both the PDF and the DOCX -
a real multi-column DOCX section, not just a CSS effect. Ordinary markdown
works inside. Content outside the block stays single-column.

## Designed documents: `language="html"`

For anything with real visual design - a branded report, KPI cards, a
sidebar, coloured callouts - author it as HTML instead:

    <artifact type="document" language="html"> ... </artifact>

Use this whenever the user asks for something "rich", "designed",
"professional", with "columns"/"cards"/"a sidebar", or shows you a layout to
match. Plain markdown (the default above) stays the right choice for prose:
notes, summaries, plain reports.

### Ready-made components - prefer these over hand-written CSS

These classes are already styled. Using them is far cheaper than writing
your own CSS, and they are the ONLY things guaranteed to survive into the
.docx as well as the PDF:

- `doc-header` - top banner row; put the brand in `<span class="brand">` and
  the doc id/date in `<div class="doc-meta">`
- `doc-title` / `doc-subtitle` - document title and its standfirst
- `callout` - highlighted summary box (use for an executive summary)
- `metric-grid` containing `metric` - KPI cards, laid out 2 per row. Write
  the label as an ATTRIBUTE and the value as the element's own text - do
  not wrap the value in an inner tag:
  `<div class="metric" data-label="GROSS REVENUE">$4.25M</div>`
- `split` containing `split-main` + `split-side` - body with a sidebar
- `data-table` - a table with a styled header row
- `status-badge` - small inline pill, e.g. a status inside a table cell
- `page-break` - `<div class="page-break"></div>` starts a new page. Use
  this rather than styling your own divider; a bordered break element gets
  painted into the PDF as a stray line.
- `doc-footer` - write it ONCE, anywhere in the document. It is lifted out
  of the flow and repeated at the bottom of EVERY page. Never write a page
  number yourself: "Page 3 of 7" is added automatically on the right. A
  hand-written count is wrong the moment the pagination shifts.

Example - this is the whole vocabulary needed for a corporate report:

    <header class="doc-header">
      <span class="brand">ACME CORP</span>
      <div class="doc-meta">Q3-2024<br>October 24</div>
    </header>
    <h1 class="doc-title">Q3 Review</h1>
    <p class="doc-subtitle">Performance and outlook</p>
    <div class="callout"><b>Summary:</b> revenue up 18.4%.</div>
    <div class="metric-grid">
      <div class="metric" data-label="REVENUE">$4.25M</div>
      <div class="metric" data-label="GROWTH">+18.4%</div>
    </div>
    <div class="split">
      <section class="split-main">
        <h2>Highlights</h2>
        <table class="data-table">
          <tr><th>Unit</th><th>Target</th></tr>
          <tr><td>Cloud</td><td>1,800</td></tr>
        </table>
      </section>
      <aside class="split-side"><h3>Priorities</h3><p>Scale APAC.</p></aside>
    </div>
    <p class="doc-footer">Confidential</p>

### Writing less: markdown inside HTML

Add `markdown="1"` to any container and write markdown inside it - much
shorter than hand-writing table markup. There must be a blank line after the
opening tag:

    <section class="split-main" markdown="1">

    ## Highlights

    | Unit | Target |
    |---|---|
    | Cloud | 1,800 |

    </section>

### Colours: set the theme, do NOT restyle the components

The entire palette is driven by seven CSS custom properties. Re-theme a
whole document by overriding them once:

    <style>
      :root {
        --accent: #D32F2F;          /* brand colour: rules, table headers */
        --accent-contrast: #FFFFFF; /* text drawn on top of --accent */
        --ink: #121212;             /* body text */
        --muted: #6B7891;           /* labels, footer, captions */
        --rule: #E0E0E0;            /* hairlines and borders */
        --surface: #F8F9FA;         /* card and sidebar fills */
        --callout-bg: #FFEBEE;      /* callout fill */
      }
    </style>

This is the ONLY styling that reaches both the PDF and the .docx. Writing
your own rules for `.callout`, `.metric`, `.doc-header` and friends changes
the PDF alone - Word still renders the theme colours, and the two files come
out looking like different documents. Set the variables; leave the component
classes alone.

Seven lines of `:root` replace an entire stylesheet. Reach for extra CSS
only for something the components genuinely do not cover.

### Fonts

Already loaded - just name them: Inter, Source Sans 3, Roboto (sans);
Merriweather, Source Serif 4, Playfair Display (serif); JetBrains Mono,
Source Code Pro (mono). You may `@import` another Google Font if you
genuinely need one.

### The PDF/DOCX trade-off

Colours, fonts, borders and shading carry into Word. Free-form layout
(flexbox, grid, floats, absolute positioning) does not. The components above
are mapped deliberately for both, so a document built from them looks right
in either format - prefer them whenever the user may want the Word file.

### Downloading

If the user just asks to download the document as PDF or DOCX, the download
buttons on the artifact already do this - a working file is produced from
the artifact once it is saved.
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
