import time
import frappe


class RateLimiter:
    """
    Connection-scoped rate limiter using Frappe cache.
    Shared across all OdooConnector instances for the same connection.
    """

    def __init__(self, connection_name: str, max_rpm: int = 60):
        self.cache_key = f"odoo_rate_limit:{connection_name}"
        self.interval = 60.0 / max_rpm

    def wait(self):
        """Block until the next request is allowed."""
        cache = frappe.cache()
        while True:
            last = float(cache.get(self.cache_key) or 0)
            now = time.time()
            elapsed = now - last
            if elapsed >= self.interval:
                cache.set(self.cache_key, str(now), ex=120)
                return
            time.sleep(self.interval - elapsed)

    def check(self) -> bool:
        """Non-blocking check if a request is allowed."""
        last = float(frappe.cache().get(self.cache_key) or 0)
        return (time.time() - last) >= self.interval
