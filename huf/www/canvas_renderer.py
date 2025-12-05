"""
Canvas Renderer
Serves canvas HTML files from www/canvas/<slug>/ directory
"""

import os
import frappe
from frappe import _
from werkzeug.exceptions import NotFound


def get_context(context):
	"""Get context for canvas page - Frappe will look for this function"""
	# Get slug from URL path
	slug = frappe.form_dict.get('slug') or frappe.local.path.split('/')[-1]
	
	if not slug:
		frappe.throw(_("Canvas slug is required"), NotFound)
	
	# Get canvas directory
	app_path = frappe.get_app_path("huf")
	canvas_dir = os.path.join(app_path, "www", "canvas", slug)
	index_html = os.path.join(canvas_dir, "index.html")
	
	if not os.path.exists(index_html):
		frappe.throw(_("Canvas not found: {0}").format(slug), NotFound)
	
	# Read HTML content
	try:
		with open(index_html, 'r', encoding='utf-8') as f:
			html_content = f.read()
	except Exception as e:
		frappe.log_error(f"Failed to read canvas file: {str(e)}")
		frappe.throw(_("Failed to load canvas"), NotFound)
	
	# Try to read CSS and JS if they exist separately
	css_content = ""
	js_content = ""
	
	css_path = os.path.join(canvas_dir, "index.css")
	if os.path.exists(css_path):
		try:
			with open(css_path, 'r', encoding='utf-8') as f:
				css_content = f.read()
		except Exception:
			pass
	
	js_path = os.path.join(canvas_dir, "index.js")
	if os.path.exists(js_path):
		try:
			with open(js_path, 'r', encoding='utf-8') as f:
				js_content = f.read()
		except Exception:
			pass
	
	# If CSS/JS are separate, inject them
	if css_content:
		# Inject CSS before </head> or at start of <body>
		if '</head>' in html_content:
			html_content = html_content.replace('</head>', f'<style>{css_content}</style></head>')
		elif '<body' in html_content:
			html_content = html_content.replace('<body', f'<style>{css_content}</style><body')
		else:
			html_content = f'<style>{css_content}</style>{html_content}'
	
	if js_content:
		# Inject JS before </body> or at end
		if '</body>' in html_content:
			html_content = html_content.replace('</body>', f'<script>{js_content}</script></body>')
		else:
			html_content = f'{html_content}<script>{js_content}</script>'
	
	# Set context for template rendering
	context.html = html_content
	context.slug = slug
	context.no_cache = 1  # Prevent caching for dynamic content
	
	return context
