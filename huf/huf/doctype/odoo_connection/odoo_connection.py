import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_url
import xmlrpc.client
import requests
import json


class OdooConnection(Document):
    def validate(self):
        if self.odoo_url:
            self.odoo_url = self.odoo_url.rstrip("/")
            if not self.odoo_url.startswith(("http://", "https://")):
                frappe.throw("Odoo URL must start with http:// or https://")

        if self.is_new() or not self.get_password("webhook_key", raise_exception=False):
            self.webhook_key = frappe.generate_hash(length=32)
        
        # Set webhook URL (without key in URL for better security, now handled in receiver)
        self.webhook_url = f"{get_url()}/api/method/huf.ai.odoo.webhook.receive_webhook?connection={self.name}"

    @frappe.whitelist()
    def test_connection(self):
        """Test the connection by calling Odoo's version() and authenticate()."""
        try:
            from huf.ai.odoo.connector import OdooConnector
            connector = OdooConnector(self.name)
            
            # OdooConnector.__init__ calls check_login() via odoo-client-lib
            # If we reached here, login was successful.
            
            # Update status
            self.connection_status = "Connected"
            self.last_tested = now_datetime()
            
            # Since OdooConnector uses odoo-client-lib, we can't easily get 
            # the raw server_version from common.version() without a direct call,
            # but we can trust the successful init.
            
            self.save()
            return {"success": True, "uid": connector.uid}

        except Exception as e:
            self.connection_status = "Failed"
            self.save()
            frappe.log_error(frappe.get_traceback(), "Odoo Connection Test Failed")
            return {"success": False, "error": str(e)}
