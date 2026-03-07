import frappe
from frappe.model.document import Document


class HufDataTable(Document):
	def validate(self):
		if not self.doctype_name and self.table_name:
			self.doctype_name = f"HT {self.table_name}"

	def on_trash(self):
		"""Clean up the associated DocType when registry entry is deleted."""
		if self.doctype_name and frappe.db.exists("DocType", self.doctype_name):
			frappe.delete_doc("DocType", self.doctype_name, force=True, ignore_permissions=True)
