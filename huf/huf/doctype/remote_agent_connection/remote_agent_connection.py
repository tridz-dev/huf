# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document


class RemoteAgentConnection(Document):
	def validate(self):
		self.validate_transport_and_url()
		self.validate_auth()
		self.validate_manifest_json()

	def validate_transport_and_url(self):
		if self.transport in ("http", "websocket"):
			if not self.base_url:
				frappe.throw(_("Base URL is required when transport is {0}.").format(self.transport))

			clean_url = self.base_url.strip()
			parsed = urlparse(clean_url)
			if not parsed.scheme or parsed.scheme.lower() not in ("http", "https", "ws", "wss"):
				frappe.throw(_("Invalid Base URL scheme. Must start with http://, https://, ws://, or wss://."))
			if not parsed.netloc:
				frappe.throw(_("Invalid Base URL format."))
			self.base_url = clean_url

	def validate_auth(self):
		if self.auth_type != "none":
			# Frappe Password fields encrypt secret automatically.
			# If creating new record or setting auth_type without secret, ensure a password exists.
			if not self.auth_secret and not self.get_password("auth_secret"):
				frappe.throw(_("Auth Secret is required when Auth Type is {0}.").format(self.auth_type))

	def validate_manifest_json(self):
		if self.manifest_json:
			try:
				if isinstance(self.manifest_json, str):
					json.loads(self.manifest_json)
			except Exception as e:
				frappe.throw(_("Invalid JSON in manifest_json: {0}").format(str(e)))

	def get_auth_secret(self) -> str | None:
		"""
		Securely retrieve the decrypted auth secret.
		Never log or return this value in API responses.
		"""
		if self.auth_type == "none":
			return None
		return self.get_password("auth_secret")

	def as_dict(self, no_nulls=False, no_default_fields=False, convert_dates_to_gstr=False, no_private_properties=False):
		"""
		Override as_dict to ensure auth_secret is never returned or leaked in dict form.
		"""
		d = super().as_dict(
			no_nulls=no_nulls,
			no_default_fields=no_default_fields,
			convert_dates_to_gstr=convert_dates_to_gstr,
			no_private_properties=no_private_properties,
		)
		if "auth_secret" in d:
			d.pop("auth_secret", None)
		return d

	@frappe.whitelist()
	def test_connection(self):
		"""
		Test reachable connection status.
		"""
		if not self.enabled:
			return {"status": "disabled", "message": _("Connection is disabled.")}

		if self.transport not in ("http", "websocket"):
			return {"status": "unknown", "message": _("Transport type '{0}' test not supported.").format(self.transport)}

		try:
			import requests

			headers = {}
			secret = self.get_auth_secret()
			if self.auth_type == "bearer_token" and secret:
				headers["Authorization"] = f"Bearer {secret}"
			elif self.auth_type == "site_token" and secret:
				headers["X-Site-Token"] = secret

			url = self.base_url.rstrip("/")
			response = requests.get(f"{url}/.well-known/huf-agent.json", headers=headers, timeout=5)
			if response.status_code == 200:
				self.health_status = "healthy"
				self.last_error = ""
				self.last_health_check = frappe.utils.now_datetime()
				self.save(ignore_permissions=True)
				return {"status": "healthy", "message": _("Connection successful.")}
			else:
				self.health_status = "degraded"
				self.last_error = f"HTTP {response.status_code}: {response.text[:200]}"
				self.last_health_check = frappe.utils.now_datetime()
				self.save(ignore_permissions=True)
				return {"status": "degraded", "message": self.last_error}
		except Exception as e:
			err_msg = str(e)
			self.health_status = "failed"
			self.last_error = err_msg[:500]
			self.last_health_check = frappe.utils.now_datetime()
			self.save(ignore_permissions=True)
			return {"status": "failed", "message": err_msg}

	@frappe.whitelist()
	def refresh_manifest(self):
		"""
		Fetch and cache the manifest JSON from remote agent.
		"""
		if not self.enabled:
			frappe.throw(_("Cannot refresh manifest on a disabled connection."))

		if not self.base_url:
			frappe.throw(_("Base URL is required to refresh manifest."))

		try:
			import requests

			headers = {}
			secret = self.get_auth_secret()
			if self.auth_type == "bearer_token" and secret:
				headers["Authorization"] = f"Bearer {secret}"
			elif self.auth_type == "site_token" and secret:
				headers["X-Site-Token"] = secret

			url = self.base_url.rstrip("/")
			response = requests.get(f"{url}/.well-known/huf-agent.json", headers=headers, timeout=10)
			response.raise_for_status()

			manifest_data = response.json()
			self.manifest_json = json.dumps(manifest_data, indent=2)
			self.health_status = "healthy"
			self.last_error = ""
			self.last_health_check = frappe.utils.now_datetime()
			self.save(ignore_permissions=True)
			return manifest_data
		except Exception as e:
			err_msg = str(e)
			self.health_status = "failed"
			self.last_error = f"Manifest refresh failed: {err_msg[:500]}"
			self.last_health_check = frappe.utils.now_datetime()
			self.save(ignore_permissions=True)
			frappe.throw(_("Failed to refresh manifest: {0}").format(err_msg))


@frappe.whitelist()
def test_connection_cmd(connection_name):
	doc = frappe.get_doc("Remote Agent Connection", connection_name)
	doc.check_permission("read")
	return doc.test_connection()


@frappe.whitelist()
def refresh_manifest_cmd(connection_name):
	doc = frappe.get_doc("Remote Agent Connection", connection_name)
	doc.check_permission("write")
	return doc.refresh_manifest()
