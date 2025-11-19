"""Custom Page Renderer for Documentation.

This module serves the static HTML documentation file without Jinja template processing.
"""

import os
import re
import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer


class DocsRenderer(BaseRenderer):
	"""Page renderer that serves static HTML documentation without Jinja processing.
	
	Routes:
	- `/huf/docs` - Serves the static docs.html file (primary route)
	- `/huf/docs/<path:path>` - Also serves the same file (for nested routes)
	- `/docs` - Serves the static docs.html file (backwards compatibility)
	- `/docs/<path:path>` - Also serves the same file (for nested routes)
	"""

	def can_render(self) -> bool:
		"""Determine if this renderer should handle the current path."""
		# Match /docs, /docs/..., /huf/docs, and /huf/docs/... paths
		return (
			self.path == "docs" 
			or self.path.startswith("docs/")
			or self.path == "huf/docs"
			or self.path.startswith("huf/docs/")
		)

	def render(self):
		"""Render the static HTML documentation file."""
		app_path = frappe.get_app_path("agentflo")
		html_file = os.path.join(app_path, "www", "docs.html")
		
		if not os.path.exists(html_file):
			return self.build_response(
				"<h1>Documentation not found</h1><p>The documentation file could not be located.</p>",
				headers={"Content-Type": "text/html; charset=utf-8"},
				http_status_code=404
			)
		
		with open(html_file, "r", encoding="utf-8") as f:
			html_content = f.read()
		
		# Remove {% raw %} and {% endraw %} tags if present
		html_content = html_content.replace("{% raw %}", "").replace("{% endraw %}", "")
		
		# DEBUG: Add a visible marker to confirm renderer is being called
		# This will appear in the page source if the renderer is working
		# Handle both <head> and <head> with attributes
		html_content = re.sub(r'<head([^>]*)>', r'<head\1><!-- DocsRenderer is working! -->', html_content, count=1)
		
		# Determine the correct base path based on the current route
		# If we're serving /huf/docs, use /huf/docs, otherwise use /docs
		if self.path.startswith("huf/docs"):
			base_path = "/huf/docs"
		else:
			base_path = "/docs"
		
		# Rewrite ALL occurrences of /assets/agentflo/docs/docs/ to the correct base path
		# This is the most common pattern for navigation links
		# We do this first with a simple string replace for the common case
		html_content = html_content.replace('/assets/agentflo/docs/docs/', base_path + '/')
		
		# Then handle the root link
		html_content = html_content.replace('href="/assets/agentflo/docs/"', f'href="{base_path}/"')
		html_content = html_content.replace("href='/assets/agentflo/docs/'", f"href='{base_path}/'")
		
		# Now use regex for more complex patterns that need to preserve asset paths
		# Pattern 1: Match href="/assets/agentflo/docs/..." but exclude asset paths
		html_content = re.sub(
			r'href=["\']/assets/agentflo/docs/(?!_next|static|docs)([^"\']*)["\']',
			f'href="{base_path}/\\1"',
			html_content
		)
		
		# Pattern 2: Handle data-href attributes
		html_content = re.sub(
			r'data-href=["\']/assets/agentflo/docs/(?!_next|static|docs)([^"\']*)["\']',
			f'data-href="{base_path}/\\1"',
			html_content
		)
		
		# Pattern 3: Handle JavaScript string literals (any quotes)
		html_content = re.sub(
			r'(["\'])/assets/agentflo/docs/(?!_next|static|docs)([^"\']*)\1',
			f'\\1{base_path}/\\2\\1',
			html_content
		)
		
		# Pattern 4: Handle Next.js __NEXT_DATA__ which might contain base paths
		# Replace assetPrefix or basePath in JSON data
		html_content = re.sub(
			r'("assetPrefix"|"basePath"):\s*["\']/assets/agentflo/docs["\']',
			f'\\1: "{base_path}"',
			html_content
		)
		
		# Note: We removed the JavaScript override script since Next.js should handle
		# client-side routing correctly with the basePath configured in next.config.js
		
		headers = {"Content-Type": "text/html; charset=utf-8"}
		return self.build_response(html_content, headers=headers)

