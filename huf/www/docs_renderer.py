"""
Custom Page Renderer for Documentation.

Serves static Next.js exported HTML files for /huf/docs
WITHOUT interfering with static assets.
"""

import os
import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer


class DocsRenderer(BaseRenderer):
    def can_render(self):
        # Never render Next.js assets
        if self.path.startswith("huf/docs/_next") or self.path.endswith((
            ".css", ".js", ".map",
            ".png", ".jpg", ".jpeg", ".svg", ".webp",
            ".woff", ".woff2", ".ttf", ".eot"
        )):
            return False
        return self.path == "huf/docs" or self.path.startswith("huf/docs/")

    def render(self):
        app_path = frappe.get_app_path("huf")
        docs_root = os.path.join(app_path, "www", "huf", "docs")

        if self.path == "huf/docs":
            html_file = os.path.join(docs_root, "index.html")
        else:
            sub_path = self.path[len("huf/docs/"):]
            html_file = os.path.join(docs_root, "docs", sub_path, "index.html")

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
