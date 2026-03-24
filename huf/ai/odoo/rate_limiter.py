import time

class RateLimiter:
    """
    Token-bucket rate limiter for Odoo API calls.
    Respects SaaS rate limits (~1 req/sec for Odoo.com by default).
    """
    
    def __init__(self, max_rpm: int = 60):
        self.max_rpm = max_rpm
        self.interval = 60.0 / max_rpm  # seconds between requests
        self.last_request = 0.0

    def wait(self):
        """Block until the next request is allowed."""
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_request = time.time()

    def check(self) -> bool:
        """Non-blocking check if a request is allowed."""
        return (time.time() - self.last_request) >= self.interval
