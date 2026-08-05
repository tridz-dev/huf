"""
Zendesk integration tools for ticket listing, retrieval, and creation.
Uses HUF Integration Settings for Zendesk credentials (username=agent email,
password=API token, company_name=subdomain). Auth follows Zendesk's token
convention: basic auth with username "<email>/token" and the API token as password.
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "zendesk"


def _get_zendesk_config():
	username = require_credential(SERVICE_NAME, "username")
	password = require_credential(SERVICE_NAME, "password")
	company_name = require_credential(SERVICE_NAME, "company_name")
	base_url = f"https://{company_name}.zendesk.com/api/v2"
	return base_url, (f"{username}/token", password)


def _make_zendesk_request(method: str, endpoint: str, json_data=None, params=None):
	base_url, auth = _get_zendesk_config()

	response = requests.request(
		method, f"{base_url}/{endpoint}", auth=auth, json=json_data, params=params, timeout=30
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def handle_list_tickets(**kwargs) -> str:
	"""List Zendesk tickets, optionally filtered by status."""
	try:
		data = _make_zendesk_request("GET", "tickets.json")

		status_filter = kwargs.get("status")
		tickets = []
		for ticket in data.get("tickets", []):
			if status_filter and ticket.get("status") != status_filter:
				continue
			tickets.append(
				{
					"id": ticket.get("id"),
					"subject": ticket.get("subject"),
					"status": ticket.get("status"),
					"priority": ticket.get("priority"),
					"requester_id": ticket.get("requester_id"),
					"created_at": ticket.get("created_at"),
				}
			)

		return json.dumps({"success": True, "count": len(tickets), "results": tickets})
	except Exception as e:
		error_msg = f"Zendesk List Tickets Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_ticket(**kwargs) -> str:
	"""Get details of a Zendesk ticket by ID."""
	try:
		ticket_id = kwargs.get("ticket_id")
		if not ticket_id:
			return json.dumps({"success": False, "error": "ticket_id is required"}, default=str)

		data = _make_zendesk_request("GET", f"tickets/{ticket_id}.json")
		ticket = data.get("ticket", {})

		ticket_data = {
			"id": ticket.get("id"),
			"subject": ticket.get("subject"),
			"description": ticket.get("description"),
			"status": ticket.get("status"),
			"priority": ticket.get("priority"),
			"requester_id": ticket.get("requester_id"),
			"assignee_id": ticket.get("assignee_id"),
			"created_at": ticket.get("created_at"),
			"updated_at": ticket.get("updated_at"),
		}

		return json.dumps({"success": True, "results": ticket_data})
	except Exception as e:
		error_msg = f"Zendesk Get Ticket Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_ticket(**kwargs) -> str:
	"""Create a Zendesk ticket."""
	try:
		subject = kwargs.get("subject")
		comment = kwargs.get("comment")
		if not all([subject, comment]):
			return json.dumps({"success": False, "error": "subject and comment are required"}, default=str)

		ticket_payload = {"subject": subject, "comment": {"body": comment}}
		priority = kwargs.get("priority")
		if priority:
			ticket_payload["priority"] = priority

		data = _make_zendesk_request("POST", "tickets.json", json_data={"ticket": ticket_payload})
		ticket = data.get("ticket", {})

		return json.dumps(
			{
				"success": True,
				"results": {
					"id": ticket.get("id"),
					"subject": ticket.get("subject"),
					"status": ticket.get("status"),
				},
			}
		)
	except Exception as e:
		error_msg = f"Zendesk Create Ticket Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
