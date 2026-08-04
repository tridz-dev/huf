# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Render markdown documents to sanitized, print-ready HTML.

This is the first stage of the markdown -> {PDF, DOCX} pipeline. The HTML output
is consumed by downstream renderers (PDF and DOCX), so the output shape and
sanitization are critical for stability.
"""

import markdown
import bleach


#: CSS stylesheet for print-ready HTML documents. Defines the selectors that
#: downstream PDF/DOCX renderers rely on. Includes paged-media syntax for
#: WeasyPrint and similar tools.
PRINT_STYLESHEET = """
body {
	font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
	font-size: 11pt;
	line-height: 1.6;
	color: #333;
}

h1 {
	font-size: 28pt;
	font-weight: bold;
	margin-top: 1em;
	margin-bottom: 0.5em;
}

h2 {
	font-size: 22pt;
	font-weight: bold;
	margin-top: 0.9em;
	margin-bottom: 0.4em;
}

h3 {
	font-size: 18pt;
	font-weight: bold;
	margin-top: 0.8em;
	margin-bottom: 0.3em;
}

h4 {
	font-size: 14pt;
	font-weight: bold;
	margin-top: 0.7em;
	margin-bottom: 0.3em;
}

h5 {
	font-size: 12pt;
	font-weight: bold;
	margin-top: 0.6em;
	margin-bottom: 0.2em;
}

h6 {
	font-size: 11pt;
	font-weight: bold;
	margin-top: 0.5em;
	margin-bottom: 0.2em;
}

blockquote {
	border-left: 4px solid #999;
	font-style: italic;
	padding-left: 1em;
	margin-left: 0;
	margin-right: 0;
	color: #666;
}

table {
	border-collapse: collapse;
	width: 100%;
	margin: 1em 0;
}

th, td {
	border: 1px solid #444;
	padding: 6px;
	text-align: left;
}

th {
	font-weight: bold;
	background-color: #f5f5f5;
}

.text-left {
	text-align: left;
}

.text-center {
	text-align: center;
}

.text-right {
	text-align: right;
}

.indent-1 {
	margin-left: 0.5in;
}

.indent-2 {
	margin-left: 1in;
}

.indent-3 {
	margin-left: 1.5in;
}

@page {
	size: A4;
	margin: 2cm;
}

@page {
	@bottom-center {
		content: counter(page);
	}
}
"""


def render_document_html(markdown_source: str, title: str = "") -> str:
	"""Render markdown to a full, sanitized, print-ready HTML document.

	Args:
		markdown_source: Markdown text to render
		title: Optional title for the HTML document

	Returns:
		A complete HTML document string with sanitized content, ready for
		conversion to PDF or DOCX.
	"""
	# Convert markdown to HTML with the required extensions
	html_body = markdown.markdown(
		markdown_source,
		extensions=["tables", "fenced_code", "attr_list", "sane_lists"]
	)

	# Define allowed tags and attributes for sanitization
	allowed_tags = [
		"p", "h1", "h2", "h3", "h4", "h5", "h6",
		"ul", "ol", "li",
		"table", "thead", "tbody", "tr", "th", "td",
		"blockquote",
		"strong", "em", "a", "img", "br", "hr",
		"pre", "code",
		"span", "div"
	]

	allowed_attributes = {
		"*": ["class"],
		"a": ["href", "title"],
		"img": ["src", "alt"]
	}

	# Sanitize the HTML to remove any dangerous content
	sanitized_body = bleach.clean(
		html_body,
		tags=allowed_tags,
		attributes=allowed_attributes,
		strip=True
	)

	# Build the complete HTML document
	html_document = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{PRINT_STYLESHEET}
</style>
</head>
<body>
{sanitized_body}
</body>
</html>
"""

	return html_document
