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
DOCUMENT_TOOL_NAME = re.compile(r"export_artifact|export_document|redline_artifact|list_document_artifacts|show_artifact", re.IGNORECASE)


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
- `metric-grid` containing `metric` - KPI cards, 2 per row by default; add
  `cols-3` or `cols-4` (`class="metric-grid cols-4"`) for a single row of 3-4
  SHORT values. Write the label as an ATTRIBUTE and the value as the
  element's own text - do not wrap the value in an inner tag:
  `<div class="metric" data-label="GROSS REVENUE">$4.25M</div>`
- `split` containing `split-main` + `split-side` - body with a narrow margin
  note (see "Sidebars" below before using it)
- `data-table` - a table with a styled header row
- `status-badge` - small inline pill, e.g. a status inside a table cell.
  Keep it to one or two words ("On track", "At risk")
- `page-break` - `<div class="page-break"></div>` starts a new page. Use
  this rather than styling your own divider; a bordered break element gets
  painted into the PDF as a stray line.
- `doc-footer` - write it ONCE, anywhere in the document. It is lifted out
  of the flow and repeated at the bottom of EVERY page. Never write a page
  number yourself: "Page 3 of 7" is added automatically on the right. A
  hand-written count is wrong the moment the pagination shifts.

### Sidebars: short notes only, never a second column of prose

`split-side` is a short margin note in small type. On an A4 page it is
stacked below the main text at full width (it only sits beside the text in
a wide view), and a long sidebar is always stacked - so it buys no space.
Do not style `.split` or `.split-side` yourself.

- Put ONLY short, glanceable content in it: 2-5 bullets or a few key facts,
  at most ~40 words, with at most one short label heading.
- NEVER put a vision statement, a paragraph of analysis, or a table in
  `split-side`. Use a full-width `callout` instead.
- Keep `data-table`s and wide markdown tables OUTSIDE any `split`, at full
  page width.
- When in doubt, skip the sidebar: a full-width `callout` plus a
  `metric-grid` reads better in the PDF, the preview and Word alike (the
  .docx stacks the sidebar under the main text anyway).

### Typography is already set - do not resize it

The stylesheet carries a calibrated, all-sans type scale (title 19.5pt, h2
13pt, h3 11pt, body 9.5pt, tables 9pt, captions 8.5pt) tuned for A4. Do not set `font-size`,
`line-height`, `padding` or `margin` on headings, paragraphs, lists or
tables; oversized headings and loose spacing are the most common way a
generated document ends up looking amateur. Structure with `##` for
sections and `###` for sub-sections; use one `doc-title` per document.

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
    <h2>Highlights</h2>
    <table class="data-table">
      <tr><th>Unit</th><th>Target</th><th>Status</th></tr>
      <tr><td>Cloud</td><td>1,800</td><td><span class="status-badge">On track</span></td></tr>
    </table>
    <div class="split">
      <section class="split-main">
        <h2>Outlook</h2>
        <p>Demand in APAC is ahead of plan; hiring is the constraint.</p>
      </section>
      <aside class="split-side"><h4>Priorities</h4>
        <ul><li>Scale APAC</li><li>Hire 12 engineers</li></ul></aside>
    </div>
    <p class="doc-footer">Confidential</p>

### Writing less: markdown inside HTML

Add `markdown="1"` to any container and write markdown inside it - much
shorter than hand-writing table markup. There must be a blank line after the
opening tag and before the closing tag:

    <section markdown="1">

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

The default is one clean sans family for everything (title, headings,
body, KPIs) - keep it. Do not switch headings or the title to a serif or
display face. If a brand needs a different sans, these are already loaded:
Inter, Source Sans 3, Roboto; mono: JetBrains Mono, Source Code Pro.

### The PDF/DOCX trade-off

Colours, fonts, borders and shading carry into Word. Free-form layout
(flexbox, grid, floats, absolute positioning) does not. The components above
are mapped deliberately for both, so a document built from them looks right
in either format - prefer them whenever the user may want the Word file.

### Downloading

If the user just asks to download the document as PDF or DOCX, the Export
menu on the artifact already does this - a working file is produced from
the artifact once it is saved.
"""

DOCUMENT_EXPORT_TOOL_INSTRUCTIONS = """
### Producing a PDF or Word file when asked - use `export_document`

If the user asks for a PDF, a Word/DOCX file, or "a report as a document"
("make this a PDF", "create a docx report"), call
`export_document(format, content=...)` (or `artifact_id_or_title=...` for a
document already in the conversation). It renders through the platform
pipeline and returns a `markdown_link`; put that link in your reply so the
user gets a download. Do NOT paste the document as plain text, and do NOT
write a script that builds the file - neither produces a download. `format`
is one of `pdf`, `docx`, `html`, `md`. Only when the tool is not available to
you, emit `<artifact type="document">` instead; its Export menu offers PDF
and DOCX.

### Exporting and redlining via tools - id sequencing matters

You also have `list_document_artifacts`, `export_artifact`, `redline_artifact`,
and `show_artifact` tools for cases where YOU (not the user clicking a
button) need to trigger an export, produce a marked-up revision, or open a
document in the user's preview pane - for example, exporting a document from
several turns ago, applying suggested edits as Word tracked changes rather
than silently rewriting the document, or surfacing a document you just
created so the user sees it immediately without clicking. `show_artifact`
takes only `artifact_id` and requires no extra step to describe.

A document artifact's id is NOT known to you at the moment you emit its
`<artifact type="document">` tag - it is only assigned after that message
is saved. You cannot call `export_artifact` or `redline_artifact` on a
document you are creating in the CURRENT response.

To export or redline a document created earlier in the conversation (by you
or by a previous turn):
1. Call `list_document_artifacts(conversation_id)` first to find its id.
2. Call `export_artifact(artifact_id, format)` with `format` one of `"pdf"`,
   `"docx"`, `"html"`, `"md"` - returns a downloadable file URL.
3. To suggest edits as Word tracked changes, call
   `redline_artifact(artifact_id, edits, author)` with `edits` as a list of
   `{"find": "...", "replace": "..."}` objects. This produces a NEW derived
   DOCX with insertions/deletions marked - it does not modify the
   artifact's own content, so the original stays intact.
"""


DESKTOP_DOCUMENT_FILE_INSTRUCTIONS_WITH_SKILLS = """
### PDF and Word files in a Huf Desktop workspace

This conversation is running on the user's own computer with a workspace. When the user asks for a PDF, a
Word/DOCX file or another office file, make a real file in THEIR workspace with the local office skills, not
a server download and not pasted text:

1. Read the `huf-office` skill (`desktop_skill_read`) and the skill for the format: `typst-doc` for a
   print-quality PDF, `docx` for a Word file (it can also do a PDF preview when LibreOffice is present).
2. Write a small spec and run the skill's script with `desktop_skill_run`. Output goes ONLY to
   `outputs/<name>` in the workspace; never pass an absolute path.
3. Report the path (`outputs/<name>`) and the script's `rung`/`approximate` result honestly. The user finds
   the file in the Activity tab, where Reveal and Open are offered. The file is not uploaded anywhere.

Use `export_document` (a server-side download) only if the user asks for a downloadable/shared file rather
than a file on their computer.
"""

DESKTOP_DOCUMENT_FILE_INSTRUCTIONS_NO_SKILLS = """
### PDF and Word files in a Huf Desktop workspace

This conversation is running on the user's own computer, but the local office skills are not enabled, so you
cannot write a PDF or Word file into their workspace. If they ask for one, say so plainly: creating PDF/DOCX
files locally needs the Office skills switched on in Huf Desktop (Settings, Local capabilities, Skills).
Do not pretend a file was made and do not write a script that would silently fail. Offer the alternative that
works now: a document artifact (its Export menu saves PDF or Word through the desktop app), or
`export_document` if you have it, for a server-side download.
"""

DESKTOP_WORKSPACE_FILE_INSTRUCTIONS = """
### Files vs inline artifacts in a Huf Desktop workspace

The user picked a workspace folder on their computer. When they ask you to create, save, write or export a
file, document, page or project (or they name a path or a file extension), write REAL files with
`desktop_write_file`: use the path they give, otherwise `outputs/<name>` (create a missing folder first with
`desktop_make_directory`), and tell them the path.
Previews, answers, charts and throwaway drafts stay inline `<artifact>` blocks.
To change an existing local file: read it (`desktop_read_file`), then use `desktop_edit_file` with the exact
text; do not re-emit it as an artifact. Never both: no duplicate inline artifact for a file you wrote.
"""
