import json
import os

import requests

BASE_URL = "https://api.telegram.org"


def handle_send_message(**kwargs):
	"""Send a message via Telegram bot."""
	try:
		token = os.getenv("TELEGRAM_TOKEN")
		if not token:
			return json.dumps({"error": "TELEGRAM_TOKEN environment variable is not set"})

		chat_id = kwargs["chat_id"]
		resp = requests.post(
			f"{BASE_URL}/bot{token}/sendMessage",
			json={"chat_id": chat_id, "text": kwargs["message"]},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "chat_id": chat_id})
	except Exception as e:
		return json.dumps({"error": str(e)})
