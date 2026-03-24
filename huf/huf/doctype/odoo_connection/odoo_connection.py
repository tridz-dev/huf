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
            url = self.odoo_url
            db = self.database_name
            username = self.username
            password = self.get_password("api_key")

            # 1. Get version info via XML-RPC (most reliable for version check)
            common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
            version_info = common.version()
            server_version = version_info.get("server_version")
            
            # 2. Authenticate
            uid = common.authenticate(db, username, password, {})
            
            if not uid:
                self.connection_status = "Auth Error"
                self.save()
                return {"success": False, "error": "Authentication failed. Check credentials."}

            # Update status
            self.connection_status = "Connected"
            self.last_tested = now_datetime()
            self.user_id = uid
            self.odoo_server_version = server_version
            
            # Auto-detect version if set to Auto Detect
            if self.odoo_version == "Auto Detect" and server_version:
                version_parts = server_version.split(".")
                if version_parts:
                    major_version = version_parts[0]
                    if major_version in ["15", "16", "17", "18", "19"]:
                        self.odoo_version = major_version
            
            self.save()
            return {"success": True, "version": server_version, "uid": uid}

        except Exception as e:
            self.connection_status = "Failed"
            self.save()
            frappe.log_error(frappe.get_traceback(), "Odoo Connection Test Failed")
            return {"success": False, "error": str(e)}
