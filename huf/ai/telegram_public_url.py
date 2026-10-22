# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Single builder for every public URL Telegram needs (webhook, Mini App, menu button, guard page).

``frappe.utils.get_url()`` appends ``webserver_port`` when the site ``host_name`` has no port, producing
``https://x.ngrok-free.app:8095``. When ``host_name`` carries a scheme it is used verbatim instead.
"""

from __future__ import annotations


def public_base_url() -> str:
	import frappe

	try:
		host = str(frappe.conf.get("host_name") or "").strip().rstrip("/")
	except Exception:
		host = ""
	if host.startswith(("https://", "http://")):
		return host
	return str(frappe.utils.get_url() or "").rstrip("/")


def public_url(path: str = "") -> str:
	"""``<public base><path>``; ``path`` may be empty or start with ``/``."""
	path = str(path or "")
	if path and not path.startswith("/"):
		path = "/" + path
	return public_base_url() + path
