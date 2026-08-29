"""Error types and error-envelope helpers for the Huf public developer API (v1).

All handlers should raise an `ApiError` subclass on failure; the router
catches these and converts them to the stable JSON error envelope via
`error_response`.
"""

from typing import Optional


class ApiError(Exception):
	"""Base class for all v1 API errors.

	Subclasses set `status_code` and `code` as class attributes; `message`
	can be overridden per-instance.
	"""

	status_code = 500
	code = "internal_error"
	default_message = "An unexpected error occurred."

	def __init__(self, message: Optional[str] = None):
		self.message = message or self.default_message
		super().__init__(self.message)


class AuthenticationError(ApiError):
	status_code = 401
	code = "authentication_required"
	default_message = "Authentication is required to access this resource."


class AuthorizationError(ApiError):
	status_code = 403
	code = "authorization_failed"
	default_message = "You are not permitted to access this resource."


class NotFoundError(ApiError):
	status_code = 404
	code = "not_found"
	default_message = "The requested resource was not found."


class ValidationError(ApiError):
	status_code = 400
	code = "validation_error"
	default_message = "The request was invalid."


class RateLimitError(ApiError):
	status_code = 429
	code = "rate_limited"
	default_message = "Too many requests. Please try again later."


def error_response(exc: ApiError, request_id: Optional[str] = None) -> dict:
	"""Build the stable JSON error envelope for an `ApiError`.

	Shape: `{"error": {"code": ..., "message": ..., "request_id": ...}}`
	"""
	return {
		"error": {
			"code": exc.code,
			"message": exc.message,
			"request_id": request_id,
		}
	}
