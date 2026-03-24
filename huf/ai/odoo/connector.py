import frappe
from typing import Any, List, Dict, Optional
from .rate_limiter import RateLimiter
from .protocols.xmlrpc import OdooXMLRPC
from .protocols.jsonrpc import OdooJSONRPC
from .protocols.json2 import OdooJSON2
from .exceptions import OdooAuthError, OdooConnectionError


class OdooConnector:
    """
    Protocol-agnostic connector to Odoo instances.
    Handles authentication, protocol selection, and rate limiting.
    """
    
    def __init__(self, connection_name: str):
        self.connection = frappe.get_doc("Odoo Connection", connection_name)
        self.url = self.connection.odoo_url
        self.db = self.connection.database_name
        self.username = self.connection.username
        self.api_key = self.connection.get_password("api_key")
        self.uid = self.connection.user_id
        
        # Initialize transport
        self.protocol = self._resolve_protocol()
        self.transport = self._init_transport()
        
        # Rate limiting
        self.rate_limiter = RateLimiter(self.connection.rate_limit_rpm or 60)

    def _resolve_protocol(self) -> str:
        if self.connection.protocol != "Auto":
            return self.connection.protocol
        
        # Default logic: JSON-2 for v19+, otherwise JSON-RPC
        if self.connection.odoo_version == "19":
            return "JSON-2"
        return "JSON-RPC"

    def _init_transport(self):
        if self.protocol == "JSON-RPC":
            return OdooJSONRPC(self.url, self.db, self.uid, self.api_key)
        elif self.protocol == "XML-RPC":
            return OdooXMLRPC(self.url, self.db, self.uid, self.api_key)
        elif self.protocol == "JSON-2":
            return OdooJSON2(self.url, self.db, self.api_key)
        else:
            return OdooJSONRPC(self.url, self.db, self.uid, self.api_key)

    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        self.rate_limiter.wait()
        if self.protocol == "JSON-2":
            return self.transport.execute(model, method, args, kwargs)
        else:
            return self.transport.execute_kw(model, method, args, kwargs)

    def search_read(self, model: str, domain: Optional[List] = None, 
                    fields: Optional[List] = None, limit: int = 80, 
                    offset: int = 0, order: Optional[str] = None) -> List[Dict]:
        return self.execute(
            model, "search_read", 
            domain or [], 
            fields=fields, 
            limit=limit, 
            offset=offset, 
            order=order
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
            attributes=attributes or ["string", "type", "required", "help", "relation"]
        )

    def get_models(self) -> List[Dict]:
        return self.search_read("ir.model", fields=["model", "name"])
