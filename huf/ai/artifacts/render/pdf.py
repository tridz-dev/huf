# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Render HTML documents to PDF bytes.

Converts full HTML documents (with paged-media CSS, print stylesheets, etc.)
produced by huf/ai/artifacts/render/html.py into PDF bytes for download or storage.

Primary path uses WeasyPrint for superior CSS support (columns, paged-media, etc.).
Fallback to Frappe's wkhtmltopdf-based get_pdf if WeasyPrint fails.
"""

import frappe


def html_to_pdf(html: str) -> bytes:
	"""Render a full HTML document to PDF bytes.

	Attempts to use WeasyPrint first for superior CSS support (paged-media,
	columns, print stylesheets). Falls back to frappe.utils.pdf.get_pdf if
	WeasyPrint raises any exception - including an ImportError, since
	WeasyPrint depends on system libraries (pango/cairo) that may be absent
	on a given deploy target even though the package itself is installed.
	The import is therefore deferred into this try block rather than done
	at module load time, so a broken WeasyPrint install cannot make this
	whole module - and the fallback path - unimportable.

	Args:
		html: A complete HTML document string (with doctype, head, body, etc.)

	Returns:
		PDF document as bytes, ready for download or storage.

	Raises:
		May raise exceptions from the fallback get_pdf if both paths fail,
		though fallback attempts to provide a best-effort PDF.
	"""
	try:
		# Primary path: WeasyPrint for excellent CSS support
		from weasyprint import HTML

		from huf.ai.artifacts.render.safety import safe_url_fetcher

		# url_fetcher is the SSRF control: document CSS is agent-authored and
		# may reference external resources, so fetching is restricted to
		# data: URLs and the allowlisted font hosts. Without it, a rule like
		# background:url(http://169.254.169.254/...) would make this worker
		# issue an attacker-chosen request from inside the network.
		pdf_bytes = HTML(string=html, url_fetcher=safe_url_fetcher).write_pdf()
		return pdf_bytes

	except Exception as e:
		# Log the WeasyPrint failure so we can track quality regressions
		frappe.log_error(
			title="WeasyPrint PDF render failed, falling back to wkhtmltopdf",
			message=f"WeasyPrint failed to render HTML document:\n{str(e)}"
		)

		# Fallback to Frappe's wkhtmltopdf-based PDF generator
		from frappe.utils.pdf import get_pdf
		return get_pdf(html)
