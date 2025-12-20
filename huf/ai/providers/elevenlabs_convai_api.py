import frappe
import requests


SETTINGS_DOCTYPE = "Elevenlabs Settings"


def _get_settings():
	"""
	Fetch ElevenLabs credentials from Single Settings DocType.
	"""

	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		frappe.throw(
			f"{SETTINGS_DOCTYPE} DocType not found",
			frappe.ValidationError
		)

	settings = frappe.get_single(SETTINGS_DOCTYPE)

	agent_id = settings.agent_id
	api_key = settings.get_password("api_key")

	return agent_id, api_key


@frappe.whitelist(allow_guest=True)
def health():
	agent_id, api_key = _get_settings()

	return {
		"status": "ok",
		"settings": {
			"hasAgentId": bool(agent_id),
			"hasApiKey": bool(api_key),
			"agentIdLength": len(agent_id) if agent_id else 0,
			"apiKeyLength": len(api_key) if api_key else 0,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_signed_url():
	agent_id, api_key = _get_settings()

	if not agent_id or not api_key:
		frappe.throw(
			"Missing Agent ID or API Key in Elevenlabs Settings",
			frappe.ValidationError
		)

	url = (
		"https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
		f"?agent_id={agent_id}"
	)

	headers = {
		"xi-api-key": api_key
	}

	response = requests.get(url, headers=headers, timeout=30)

	if not response.ok:
		try:
			error_json = response.json()
			if error_json.get("detail", {}).get("status") == "missing_permissions":
				frappe.throw(
					"ElevenLabs API key is missing convai_write permission",
					frappe.PermissionError
				)
		except Exception:
			pass

		frappe.throw(
			f"ElevenLabs API error ({response.status_code})",
			frappe.ValidationError
		)

	data = response.json()
	return {"signedUrl": data.get("signed_url")}


@frappe.whitelist(allow_guest=True)
def get_agent_id():
	agent_id, _ = _get_settings()
	return {"agentId": agent_id}
