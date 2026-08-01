"""
huf/ai/session_api.py

Whitelisted endpoint to refresh a stale CSRF token without a full page reload.

The frontend caches ``window.csrf_token`` from the initial page render
(huf/www/huf.py). Frappe regenerates the session's real CSRF token
independently of that render (frappe.sessions.generate_csrf_token), so a
long-open tab can end up sending a stale token on writes and get a 400
CSRFTokenError even though its session cookie is still perfectly valid. This
endpoint lets the frontend fetch the current token for its own (already
authenticated) session and retry instead of forcing a hard refresh.
"""

import frappe


@frappe.whitelist()
def get_csrf_token():
	return frappe.sessions.get_csrf_token()
