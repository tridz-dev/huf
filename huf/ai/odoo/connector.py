import frappe
from typing import Any, List, Dict, Optional
from .rate_limiter import RateLimiter
from .exceptions import OdooAuthError, OdooConnectionError

import odoo_client_lib as odoo_lib


class OdooConnector:
	"""
	Protocol-agnostic connector to Odoo instances.
	Uses odoo-client-lib for transport; handles rate limiting.
	"""

	def __init__(self, connection_name: str):
		self.connection = frappe.get_doc("Odoo Connection", connection_name)
		self.url = self.connection.odoo_url
		self.db = self.connection.database_name
		self.username = self.connection.username
		self.api_key = self.connection.get_password("api_key")
		self.uid = self.connection.user_id

		# Let odoo-client-lib pick the right protocol
		protocol = self._resolve_protocol_string()
		try:
			self._conn = odoo_lib.get_connection(
				hostname=self.url.rstrip("/"),
				protocol=protocol,
				database=self.db,
				login=self.username,
				password=self.api_key,
			)
			self._conn.check_login(force=False)
		except Exception as e:
			raise OdooConnectionError(f"Failed to connect: {e}") from e

		self.rate_limiter = RateLimiter(connection_name, self.connection.rate_limit_rpm or 60)

	def _resolve_protocol_string(self) -> str:
		"""Map our DocType field values to odoo-client-lib protocol strings."""
		explicit = self.connection.protocol
		if explicit and explicit != "Auto":
			return {
				"JSON-RPC": "jsonrpc",
				"XML-RPC": "xmlrpc",
				"JSON-2": "json2",
			}.get(explicit, "jsonrpc")

		version = self.connection.odoo_version
		try:
			if version and version != "Auto Detect" and int(version) >= 19:
				return "json2"
		except (ValueError, TypeError):
			pass
		return "jsonrpc"

	def execute(self, model: str, method: str, *args, **kwargs) -> Any:
		self.rate_limiter.wait()
		model_proxy = self._conn.get_model(model)
		return getattr(model_proxy, method)(*args, **kwargs)

	# --- Public helpers (unchanged signatures) ---

	def search_read(self, model: str, domain: Optional[List] = None,
	                fields: Optional[List] = None, limit: int = 80,
	                offset: int = 0, order: Optional[str] = None) -> List[Dict]:
		return self.execute(
			model, "search_read",
			domain or [],
			fields=fields, limit=limit, offset=offset, order=order,
		)

	def create(self, model: str, values: Dict) -> int:
		return self.execute(model, "create", [values])

	def write(self, model: str, ids: List[int], values: Dict) -> bool:
		return self.execute(model, "write", [ids, values])

	def unlink(self, model: str, ids: List[int]) -> bool:
		return self.execute(model, "unlink", [ids])

	def fields_get(self, model: str, attributes: Optional[List] = None) -> Dict:
		return self.execute(
			model, "fields_get", [],
			attributes=attributes or ["string", "type", "required", "help", "relation"],
		)

	def get_models(self) -> List[Dict]:
		return self.search_read("ir.model", fields=["model", "name"])
