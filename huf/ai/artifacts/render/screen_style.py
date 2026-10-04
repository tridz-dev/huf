# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Editorial screen stylesheet for document preview rendering.

This stylesheet is scoped to @media screen so PDF/print output remains
completely unaffected. It defines a calm, Notion-like reading experience
optimized for on-screen preview in the artifact pane.
"""

#: CSS stylesheet for on-screen document preview. All rules are wrapped in
#: @media screen { ... } so print output (PDF/DOCX) is completely untouched.
#: This stylesheet is appended AFTER the print stylesheet and components CSS,
#: so it inherits all color tokens and base font setup.
SCREEN_STYLESHEET = """
@media screen {
	/* Light palette is the default; hosts set data-theme="light"|"dark" on <html>. */
	:root {
		--ink: #16294D;
		--muted: #6B7891;
		--rule: #D9E0EC;
		--surface: #F7FAFD;
		--callout-bg: #EAF2FD;
		--accent: #2C5AA8;
		color-scheme: light;
	}

	html { background-color: #FFFFFF; }

	:root[data-theme="dark"] {
		--ink: #ECECEE;
		--muted: #A0A3AB;
		--rule: #2E3036;
		--surface: #1B1C20;
		--callout-bg: #1F2A3D;
		--accent: #7FA6E8;
		color-scheme: dark;
	}

	:root[data-theme="dark"] { background-color: #0F1013; }

	@media (prefers-color-scheme: dark) {
		:root:not([data-theme="light"]) {
			--ink: #ECECEE;
			--muted: #A0A3AB;
			--rule: #2E3036;
			--surface: #1B1C20;
			--callout-bg: #1F2A3D;
			--accent: #7FA6E8;
			color-scheme: dark;
			background-color: #0F1013;
		}
	}

	/* Body: measure and rhythm */
	body {
		max-width: 720px;
		margin: 0 auto;
		padding: 48px 24px 96px;
		font-family: 'Source Sans 3', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
		font-size: 17px;
		line-height: 1.65;
		color: var(--ink);
	}

	/* Headings: serif font family, weight 600 (not bold), controlled spacing */
	h1, h2, h3, h4, h5, h6 {
		font-family: 'Source Serif 4', Charter, 'Iowan Old Style', Georgia, serif;
		font-weight: 600;
		color: var(--ink);
	}

	/* Title block: body > h1:first-child */
	body > h1:first-child {
		font-size: 36px;
		line-height: 1.2;
		margin-bottom: 0.25em;
		margin-top: 0;
		margin-left: 0;
		margin-right: 0;
	}

	/* Byline: body > h1:first-child + p (immediately following paragraph) */
	body > h1:first-child + p {
		font-size: 14px;
		color: var(--muted);
		margin-bottom: 2em;
		padding-bottom: 1.25em;
		border-bottom: 1px solid var(--rule);
		font-weight: normal;
	}

	/* Byline: ensure em is not italic */
	body > h1:first-child + p em {
		font-style: normal;
	}

	h1 {
		font-size: 32px;
		line-height: 1.2;
	}

	h2 {
		font-size: 24px;
		margin-top: 2em;
		margin-bottom: 0.5em;
		border-bottom: 1px solid var(--rule);
		padding-bottom: 0.5em;
	}

	h3 {
		font-size: 19px;
	}

	h4, h5 {
		font-size: 16px;
	}

	h6 {
		font-size: 16px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}

	/* Paragraph, list rhythm */
	p, ul, ol {
		margin: 0 0 1.1em 0;
	}

	li {
		margin: 0.35em 0;
	}

	ul ul, ol ol, ul ol, ol ul {
		margin-top: 0.35em;
	}

	/* Blockquote: left border, no italic, normal weight */
	blockquote {
		border-left: 3px solid var(--rule);
		padding-left: 1em;
		margin: 1.5em 0;
		color: var(--ink);
		font-style: normal;
		font-weight: normal;
	}

	/* Code: inline and block */
	code {
		background: var(--surface);
		padding: 0.15em 0.35em;
		border-radius: 4px;
		font-size: 0.9em;
	}

	pre {
		background: var(--surface);
		padding: 14px 16px;
		border-radius: 8px;
		overflow-x: auto;
		white-space: pre;
		font-size: 0.9em;
	}

	pre code {
		background: none;
		padding: 0;
		border-radius: 0;
		font-size: 1em;
	}

	/* Tables: borders, rhythm, numeric alignment */
	table {
		border-collapse: collapse;
		font-variant-numeric: tabular-nums;
	}

	th {
		font-size: 13px;
		font-weight: 600;
		color: var(--muted);
		border: 0;
		border-bottom: 1px solid var(--rule);
		padding: 10px 12px;
		background: none;
		text-align: left;
	}

	td {
		border: 0;
		border-bottom: 1px solid var(--rule);
		padding: 10px 12px;
	}

	/* Remove border from last row */
	tbody tr:last-child td {
		border-bottom: none;
	}
}
"""
