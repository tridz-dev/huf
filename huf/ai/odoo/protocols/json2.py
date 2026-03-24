import requests
from typing import Any
from ..exceptions import OdooJSON2Error

class OdooJSON2:
    """JSON-2 API transport for Odoo 19+."""
    
    def __init__(self, url: str, db: str, api_key: str):
        self.url = url
        self.db = db
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if db:
            self.headers["X-Odoo-Database"] = db

    def execute(self, model: str, method: str, args: list = None, kwargs: dict = None) -> Any:
        payload = {}
        if args:
            payload["args"] = args
        if kwargs:
            payload.update(kwargs)
        
        resp = requests.post(
            f"{self.url}/json/2/{model}/{method}",
            json=payload,
            headers=self.headers,
            timeout=30
        )
        if resp.status_code >= 400:
            error_data = {}
            try:
                if resp.headers.get("content-type", "").startswith("application/json"):
                    error_data = resp.json()
            except Exception:
                pass
            raise OdooJSON2Error(resp.status_code, error_data)
        
        return resp.json().get("result")
