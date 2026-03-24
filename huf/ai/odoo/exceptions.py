class OdooConnectionError(Exception):
	"""Raised when connection to Odoo fails."""
	pass


class OdooAuthError(Exception):
	"""Raised when Odoo authentication fails."""
	pass


class OdooModelNotFoundError(Exception):
	"""Raised when a requested model does not exist in Odoo."""
	pass


class OdooRateLimitError(Exception):
	"""Raised when Odoo rate limit is exceeded."""
	pass
