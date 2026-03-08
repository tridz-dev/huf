# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt
"""
Installation script for HUF app.
Registers built-in integration services during installation.
"""

import frappe
import json
from frappe import _


def after_install():
    """
    Called after the app is installed.
    Registers built-in integration services and sets up default data.
    """
    register_integration_services()
    sync_tool_types()
    frappe.msgprint(_("HUF installed successfully. Integration services have been registered."))


def before_uninstall():
    """
    Called before the app is uninstalled.
    Cleanup tasks if needed.
    """
    pass


def after_app_install(app_name):
    """
    Called after any app is installed.
    """
    if app_name == "huf":
        register_integration_services()


def register_integration_services():
    """
    Register built-in integration services in the Integration Service DocType.
    These services represent external APIs that agents can interact with.
    """
    
    # Define all built-in services with their required credentials
    services = [
        # Communication Tools
        {
            "service_name": "slack",
            "category": "Communication",
            "description": "Slack messaging and channel management",
            "required_credentials": [{"key": "token", "label": "Slack Bot Token", "required": True}]
        },
        {
            "service_name": "discord",
            "category": "Communication",
            "description": "Discord bot for messaging and channel management",
            "required_credentials": [{"key": "bot_token", "label": "Discord Bot Token", "required": True}]
        },
        {
            "service_name": "telegram",
            "category": "Communication",
            "description": "Telegram bot for messaging",
            "required_credentials": [{"key": "token", "label": "Telegram Bot Token", "required": True}]
        },
        
        # Developer Tools
        {
            "service_name": "github",
            "category": "Developer",
            "description": "GitHub API for repository and issue management",
            "required_credentials": [{"key": "access_token", "label": "GitHub Access Token", "required": True}]
        },
        
        # Project Management Tools
        {
            "service_name": "jira",
            "category": "Project Management",
            "description": "Jira issue tracking and project management",
            "required_credentials": [
                {"key": "server_url", "label": "Jira Server URL", "required": True},
                {"key": "username", "label": "Username", "required": True},
                {"key": "token", "label": "API Token", "required": True}
            ]
        },
        {
            "service_name": "linear",
            "category": "Project Management",
            "description": "Linear issue tracking for modern teams",
            "required_credentials": [{"key": "api_key", "label": "Linear API Key", "required": True}]
        },
        
        # Search Tools
        {
            "service_name": "tavily",
            "category": "Search",
            "description": "Tavily AI-optimized web search",
            "required_credentials": [{"key": "api_key", "label": "Tavily API Key", "required": True}]
        },
        
        # Google Tools
        {
            "service_name": "gmail",
            "category": "Google",
            "description": "Gmail email management",
            "required_credentials": [
                {"key": "access_token", "label": "Access Token", "required": True}
            ]
        },
    ]
    
    # Create or update each service
    for service_data in services:
        try:
            # Check if service already exists
            if frappe.db.exists("Integration Service", service_data["service_name"]):
                # Update existing service
                doc = frappe.get_doc("Integration Service", service_data["service_name"])
                doc.category = service_data["category"]
                doc.description = service_data["description"]
                doc.required_credentials = json.dumps(service_data["required_credentials"])
                doc.is_builtin = 1
                doc.save()
            else:
                # Create new service
                doc = frappe.get_doc({
                    "doctype": "Integration Service",
                    "service_name": service_data["service_name"],
                    "category": service_data["category"],
                    "description": service_data["description"],
                    "required_credentials": json.dumps(service_data["required_credentials"]),
                    "is_builtin": 1
                })
                doc.insert()
                
        except Exception as e:
            frappe.log_error(f"Failed to register integration service {service_data['service_name']}: {e}")
            continue
    
    frappe.db.commit()


def sync_tool_types():
    """
    Ensure that all tool type categories from the registry exist as Agent Tool Type documents.
    """
    from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS
    
    # Extract unique categories
    categories = set()
    for tool in ALL_INTEGRATION_TOOLS:
        category = tool.get("category", "Other")
        categories.add(category)
    
    # Create or verify each category exists as Agent Tool Type
    for category in categories:
        try:
            if not frappe.db.exists("Agent Tool Type", category):
                doc = frappe.get_doc({
                    "doctype": "Agent Tool Type",
                    "name1": category
                })
                doc.insert()
        except Exception as e:
            frappe.log_error(f"Failed to create tool type {category}: {e}")
            continue
    
    frappe.db.commit()
