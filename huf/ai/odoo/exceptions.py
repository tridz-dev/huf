class OdooConnectionError(Exception):
    """Failed to connect to Odoo instance."""
    pass

class OdooAuthError(Exception):
    """Authentication failed."""
    pass

class OdooRPCError(Exception):
    """Error returned by Odoo RPC call."""
    def __init__(self, error_data: dict):
        self.code = error_data.get("code")
        self.message = error_data.get("message", "Unknown RPC error")
        self.data = error_data.get("data", {})
        super().__init__(self.message)

class OdooJSON2Error(Exception):
    """Error from JSON-2 API with HTTP status code."""
    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_name = error_data.get("error", {}).get("name", "")
        self.message = error_data.get("error", {}).get("message", f"HTTP {status_code}")
        super().__init__(self.message)

class OdooRateLimitError(Exception):
    """Rate limit exceeded."""
    pass

class OdooModelNotFoundError(Exception):
    """Target model doesn't exist in the Odoo database."""
    pass
