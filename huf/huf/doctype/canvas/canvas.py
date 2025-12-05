# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import os
import shutil
import frappe
from frappe.model.document import Document


class Canvas(Document):
	"""Canvas DocType controller"""
	
	def validate(self):
		"""Validate before save"""
		# Ensure slug is URL-safe
		if self.slug:
			import re
			self.slug = re.sub(r'[^a-z0-9_-]', '_', self.slug.lower())
	
	def after_insert(self):
		"""Create directory and copy starter template"""
		self._ensure_canvas_directory()
	
	def on_update(self):
		"""Ensure directory exists on update"""
		self._ensure_canvas_directory()
	
	def _ensure_canvas_directory(self):
		"""Create canvas directory and copy starter template if needed"""
		if not self.slug:
			return
		
		# Get paths
		app_name = "huf"
		app_path = frappe.get_app_path(app_name)
		canvas_dir = os.path.join(app_path, "www", "canvas", self.slug)
		
		# Create directory
		os.makedirs(canvas_dir, exist_ok=True)
		
		# Check if starter template needed
		index_html = os.path.join(canvas_dir, "index.html")
		if os.path.exists(index_html):
			return  # Already initialized
		
		# Copy starter template
		starter_dir = os.path.join(app_path, "templates", "canvas", "default")
		if not os.path.exists(starter_dir):
			frappe.throw(f"Starter template not found: {starter_dir}")
		
		for filename in os.listdir(starter_dir):
			src = os.path.join(starter_dir, filename)
			dst = os.path.join(canvas_dir, filename)
			if os.path.isfile(src):
				shutil.copy2(src, dst)
		
		frappe.msgprint(f"Canvas directory created at: www/canvas/{self.slug}")


def after_insert(doc, method=None):
	"""Hook function called after Canvas is inserted"""
	doc._ensure_canvas_directory()


def on_update(doc, method=None):
	"""Hook function called when Canvas is updated"""
	doc._ensure_canvas_directory()


@frappe.whitelist()
def reset_to_starter(canvas_name):
	"""Reset canvas to starter template"""
	canvas = frappe.get_doc("Canvas", canvas_name)
	
	if not canvas.allow_editing:
		frappe.throw("Editing not allowed for this canvas")
	
	# Delete existing directory
	app_path = frappe.get_app_path("huf")
	canvas_dir = os.path.join(app_path, "www", "canvas", canvas.slug)
	
	if os.path.exists(canvas_dir):
		shutil.rmtree(canvas_dir)
	
	# Recreate from starter
	canvas._ensure_canvas_directory()
	
	return {"success": True, "message": "Canvas reset to starter template"}
