import requests
from typing import Any
from ..exceptions import OdooRPCError

class OdooJSONRPC:
    """JSON-RPC transport for Odoo."""
    
    def __init__(self, url: str, db: str, uid: int, api_key: str):
        self.url = url
        self.db = db
        self.uid = uid
        self.api_key = api_key
        self._request_id = 0

    def _call(self, service: str, method: str, args: list) -> Any:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args
            },
            "id": self._request_id
        }
        resp = requests.post(f"{self.url}/jsonrpc", json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            raise OdooRPCError(result["error"])
        return result.get("result")

    def authenticate(self, username: str) -> int:
        return self._call("common", "login", [self.db, username, self.api_key])

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict = None) -> Any:
        return self._call("object", "execute_kw",
                          [self.db, self.uid, self.api_key, model, method, args, kwargs or {}])
