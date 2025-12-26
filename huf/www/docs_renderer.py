import os
import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from frappe import local

class DocsRenderer(BaseRenderer):
	def can_render(self):
		req = frappe.local.request
		if not req:
			return False

		path = req.path.lstrip("/")

		# Ignore React Server Components & Next internals
		if "_rsc=" in req.query_string.decode():
			return False

		# Ignore assets
		if path.startswith(("assets/", "files/")):
			return False

		if path.endswith((
			".css", ".js", ".map", ".png", ".jpg", ".svg",
			".woff", ".woff2", ".ttf", ".eot", ".txt"
		)):
			return False

		return path == "huf/docs" or path.startswith("huf/docs/")

	def render(self):
		req=frappe.local.request
		path=req.path.lstrip("/")
		app_path=frappe.get_app_path("huf")
		docs_root = os.path.join(app_path, "www", "huf", "docs")

		if path == "huf/docs":
			html_file = os.path.join(docs_root, "index.html")
		else:
			sub_path = path[len("huf/docs/"):]  # e.g., "installation"
			html_file = os.path.join(docs_root, sub_path, "index.html")

		if not os.path.exists(html_file):
			html_file = os.path.join(docs_root, "index.html")
			if not os.path.exists(html_file):
				return self.build_response(
					"<h1>Documentation not found</h1>",
					http_status_code=404,
					headers={"Content-Type": "text/html; charset=utf-8"},
				)

		with open(html_file, "r", encoding="utf-8") as f:
			html = f.read()

		html = html.replace("{% raw %}", "").replace("{% endraw %}", "")

		return self.build_response(
			html,
			headers={"Content-Type": "text/html; charset=utf-8"},
		)
