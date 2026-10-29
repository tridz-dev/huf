"""Pure error classification helpers for MCP calls (status codes, timeouts, retry-after).

``huf.ai.mcp_client`` imports these names.
"""

import asyncio


def _has_status_code(exc, code: str) -> bool:
    if code in str(exc):
        return True
    if hasattr(exc, "exceptions"):
        for sub_exc in exc.exceptions:
            if _has_status_code(sub_exc, code):
                return True
    return False

def _format_mcp_error(exc) -> str:
    import httpx
    if hasattr(exc, "exceptions"):
        return " | ".join(_format_mcp_error(e) for e in exc.exceptions)
    if isinstance(exc, httpx.HTTPStatusError):
        msg = str(exc)
        try:
            if hasattr(exc.response, "text") and exc.response.text:
                msg += f" (Response: {exc.response.text})"
        except (AttributeError, ValueError, RuntimeError):
            pass # Ignore if streaming response not read
        return msg
    return str(exc)


def _is_timeout_error(exc) -> bool:
    """True if `exc` (or a sub-exception) is a timeout; the server may have acted on the request."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if type(exc).__name__ in ("ReadTimeout", "TimeoutException", "WriteTimeout", "PoolTimeout", "ConnectTimeout"):
        return True
    return any(_is_timeout_error(e) for e in getattr(exc, "exceptions", ()) or ())


def _is_retryable_status(exc) -> bool:
    """True if `exc` (or any of its sub-exceptions, e.g. an ExceptionGroup)
    carries an HTTP 429 or 5xx status code."""
    if _has_status_code(exc, "429"):
        return True
    return any(_has_status_code(exc, str(code)) for code in range(500, 600))


def _extract_retry_after_seconds(exc) -> float | None:
    """Best-effort extraction of a `Retry-After` header (seconds) from `exc`.

    Looks at `exc.response.headers` (the shape `httpx.HTTPStatusError` and
    similar exceptions carry) and recurses into `exc.exceptions` for
    exception groups. Returns None if no usable header is found.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except (TypeError, ValueError):
                pass

    if hasattr(exc, "exceptions"):
        for sub_exc in exc.exceptions:
            value = _extract_retry_after_seconds(sub_exc)
            if value is not None:
                return value

    return None


def _is_generic_mcp_error(exc) -> bool:
    """mcp>=2 reports HTTP failures (e.g. 401) as a status-less MCPError."""
    if "Server returned an error response" in str(exc):
        return True
    return any(_is_generic_mcp_error(e) for e in getattr(exc, "exceptions", ()) or ())
