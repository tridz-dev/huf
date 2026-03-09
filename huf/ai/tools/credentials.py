# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# Integration credentials helper - HUF-native credential management

import os
import frappe


def require_credential(service: str, key: str) -> str:
	"""
	Retrieve a credential value for a given service and key.
	
	First checks HUF credential storage (HUF Settings DocType), 
	then falls back to environment variables.
	
	Args:
		service: The service name (e.g., "openai", "slack", "github")
		key: The credential key name (e.g., "api_key", "client_id")
	
	Returns:
		The credential value as a string
	
	Raises:
		ValueError: If the credential is not found in either HUF settings or environment
	"""
	# First, try to get from Integration Settings DocType
	try:
		integration = frappe.get_all(
			"Integration Settings",
			filters={"service": service, "is_active": 1},
			fields=["name"],
			order_by="is_default DESC, modified DESC",
			limit=1,
		)
		if integration:
			doc = frappe.get_doc("Integration Settings", integration[0].name)
			for cred in doc.credentials:
				if cred.key == key:
					return cred.get_password("value")
	except Exception:
		pass
	
	# Fallback to environment variable
	# Construct env var name: SERVICE_KEY (uppercase, underscore separated)
	env_var_name = f"{service.upper()}_{key.upper()}"
	value = os.getenv(env_var_name)
	
	if value:
		return value
	
	# Also try common alternative naming patterns
	alt_names = _get_alt_env_names(service, key)
	for alt_name in alt_names:
		value = os.getenv(alt_name)
		if value:
			return value
	
	# If still not found, raise error
	raise ValueError(
		f"Credential not found for service '{service}', key '{key}'. "
		f"Please set it in HUF Settings or via environment variable '{env_var_name}'"
	)


def _get_alt_env_names(service: str, key: str) -> list:
	"""Get alternative environment variable names for common services."""
	alt_names = []
	
	# Common patterns
	if key == "api_key":
		alt_names.append(f"{service.upper()}_API_KEY")
		alt_names.append(f"{service.upper()}_TOKEN")
		alt_names.append(f"{service.upper()}_KEY")
	elif key == "access_token":
		alt_names.append(f"{service.upper()}_ACCESS_TOKEN")
		alt_names.append(f"{service.upper()}_TOKEN")
	elif key == "client_id":
		alt_names.append(f"{service.upper()}_CLIENT_ID")
		alt_names.append(f"{service.upper()}_ID")
	elif key == "client_secret":
		alt_names.append(f"{service.upper()}_CLIENT_SECRET")
		alt_names.append(f"{service.upper()}_SECRET")
	
	# Service-specific patterns
	service_patterns = {
		"openai": ["OPENAI_API_KEY"],
		"anthropic": ["ANTHROPIC_API_KEY"],
		"slack": ["SLACK_BOT_TOKEN", "SLACK_TOKEN"],
		"github": ["GITHUB_TOKEN"],
		"google": [
			"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
			"GOOGLE_MAPS_API_KEY"
		],
		"aws": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"],
		"baidu": ["BAIDU_API_KEY"],
		"brave": ["BRAVE_API_KEY"],
		"calcom": ["CALCOM_API_KEY"],
		"clickup": ["CLICKUP_API_KEY", "CLICKUP_SPACE_ID"],
		"giphy": ["GIPHY_API_KEY"],
		"linear": ["LINEAR_API_KEY"],
		"notion": ["NOTION_API_KEY", "NOTION_DATABASE_ID"],
		"openweather": ["OPENWEATHER_API_KEY"],
		"reddit": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
		"serpapi": ["SERP_API_KEY"],
		"serper": ["SERPER_API_KEY"],
		"shopify": ["SHOPIFY_SHOP_NAME", "SHOPIFY_ACCESS_TOKEN"],
		"tavily": ["TAVILY_API_KEY"],
		"trello": ["TRELLO_API_KEY", "TRELLO_TOKEN"],
		"unsplash": ["UNSPLASH_ACCESS_KEY"],
		"youtube": ["YOUTUBE_API_KEY"],
		"zendesk": ["ZENDESK_USERNAME", "ZENDESK_PASSWORD", "ZENDESK_COMPANY_NAME"],
		"zoom": ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"],
	}
	
	if service in service_patterns:
		for pattern in service_patterns[service]:
			if pattern not in alt_names:
				alt_names.append(pattern)
	
	return alt_names


def get_credential(service: str, key: str, default: str = None) -> str:
	"""
	Get a credential value, returning default if not found (doesn't raise).
	
	Args:
		service: The service name
		key: The credential key name
		default: Default value to return if credential not found
	
	Returns:
		The credential value or default
	"""
	try:
		return require_credential(service, key)
	except ValueError:
		return default


def update_last_error(service: str, error: str):
	"""
	Update the last_error field in Integration Settings for a service.
	
	Args:
		service: The service name
		error: The error message (will be truncated to 140 chars)
	"""
	try:
		# Find active integration settings for the service
		settings = frappe.get_all(
			"Integration Settings",
			filters={"service": service, "is_active": 1},
			fields=["name"],
			order_by="is_default DESC, modified DESC",
			limit=1
		)
		
		if settings:
			doc = frappe.get_doc("Integration Settings", settings[0].name)
			doc.last_error = error[:140]  # Truncate to field length
			doc.save(ignore_permissions=True)
			frappe.db.commit()
	except Exception:
		# Silently fail - don't break tool execution for logging errors
		pass
