import xmlrpc.client
from typing import Any

class OdooXMLRPC:
    """XML-RPC transport for Odoo."""
    
    def __init__(self, url: str, db: str, uid: int, api_key: str):
        self.common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        self.db = db
        self.uid = uid
        self.api_key = api_key

    def authenticate(self, username: str) -> int:
        return self.common.authenticate(self.db, username, self.api_key, {})

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict = None) -> Any:
        return self.models.execute_kw(
            self.db, self.uid, self.api_key,
            model, method, args, kwargs or {}
        )

    def version(self) -> dict:
        return self.common.version()
