# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import secrets
from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document
from frappe.utils import get_url, now_datetime


WEBHOOK_SETUP_COOLDOWN_MINUTES = 5


class IntegrationSettings(Document):
	"""
	Integration Settings document for storing credentials for external services.
	Links to Integration Service and stores credentials in a child table.
	"""
	
	def validate(self):
		"""Validate that credentials are provided when service is set."""
		if not self.service:
			frappe.throw("Integration Service is required")
		
		# Ensure at least one credential is provided
		if not self.credentials:
			frappe.throw("At least one credential is required")

		self._ensure_telegram_webhook_config()
	
	def on_update(self):
		"""Optional auto-setup of Telegram webhook after save.

		To avoid Telegram rate limits (HTTP 429), setWebhook is only called when
		the bot configuration actually changed or when the document is new, and
		never more than once per cooldown period.
		"""
		if not (self.service == "telegram" and self.is_active and self.telegram_auto_setup_webhook):
			return

		if self._should_setup_telegram_webhook():
			self._setup_telegram_webhook()
	
	def _should_setup_telegram_webhook(self) -> bool:
		"""Return True if Telegram webhook should be re-registered."""
		if self.is_new():
			return True

		url_changed = self.has_value_changed("telegram_webhook_url")
		other_config_changed = (
			self.has_value_changed("telegram_agent")
			or self.has_value_changed("telegram_auto_setup_webhook")
			or self.has_value_changed("credentials")
		)

		# Always re-register immediately when the URL changed (e.g. port fix)
		if url_changed:
			return True

		if not other_config_changed:
			return False

		# Respect cooldown for non-URL changes to avoid Telegram rate limits
		if self._is_webhook_setup_cooldown_active():
			frappe.log_error(
				f"Skipped Telegram webhook setup for {self.name}: cooldown active",
				"Telegram Webhook"
			)
			return False

		return True

	def _is_webhook_setup_cooldown_active(self) -> bool:
		"""Return True if we already attempted setup within the cooldown window."""
		last_setup = self.telegram_last_webhook_setup
		if not last_setup:
			return False
		try:
			cooldown_end = last_setup + timedelta(minutes=WEBHOOK_SETUP_COOLDOWN_MINUTES)
			return now_datetime() < cooldown_end
		except Exception:
			return False
	
	def get_credential(self, key: str) -> str:
		"""Get a specific credential value by key."""
		for cred in self.credentials:
			if cred.key == key:
				return cred.get_password("value")
		return None
	
	def get_all_credentials(self) -> dict:
		"""Get all credentials as a dictionary."""
		return {cred.key: cred.get_password("value") for cred in self.credentials}

	def _ensure_telegram_webhook_config(self):
		"""Generate webhook secret and URL for Telegram bots."""
		if self.service != "telegram":
			return

		if not self.telegram_webhook_secret:
			self.telegram_webhook_secret = secrets.token_urlsafe(32)

		current_url = self.telegram_webhook_url or ""
		expected_url = self._get_telegram_webhook_url()

		# Regenerate if missing, empty, or contains an internal port like :8701
		if not current_url or "/:" in current_url or current_url != expected_url:
			self.telegram_webhook_url = expected_url

	def _get_telegram_webhook_url(self) -> str:
		"""Build the public webhook URL for this Telegram bot configuration.

		Uses the site's public host_name from site_config if available, otherwise
		falls back to get_url(). Strips any internal webserver port so Telegram
		receives a clean public HTTPS URL.

		The URL only contains the non-secret document name. The actual webhook
		secret is sent by Telegram in the X-Telegram-Bot-Api-Secret-Token header.
		"""
		# Prefer the explicitly configured public host name
		base_url = frappe.get_conf().get("host_name") or get_url()
		if not base_url:
			return ""

		base_url = base_url.rstrip("/")

		# If get_url() included an internal port (e.g. :8701), remove it for
		# public HTTPS webhooks. Telegram only speaks to 443 by default.
		if ":" in base_url.replace("://", ""):
			# Keep standard https/http ports; strip non-standard ones
			protocol, rest = base_url.split("://", 1)
			host_part = rest.split("/", 1)[0]
			if ":" in host_part:
				host, port = host_part.rsplit(":", 1)
				if port not in ("443", "80"):
					base_url = f"{protocol}://{host}"

		return (
			f"{base_url}/api/method/huf.ai.tools.telegram_webhook.handle_update"
			f"?doc={self.name}"
		)

	@frappe.whitelist()
	def setup_telegram_webhook(self):
		"""Manual server action to register the Telegram webhook."""
		if self.service != "telegram":
			frappe.throw("This action is only available for Telegram integrations.")
		if not self.is_active:
			frappe.throw("Integration Settings must be active.")

		# Allow manual setup to bypass the auto-setup cooldown, but still warn if
		# it was attempted very recently to protect against accidental double-clicks.
		if self._is_webhook_setup_cooldown_active() and not self.has_value_changed("telegram_webhook_url"):
			remaining = self._webhook_cooldown_remaining_minutes()
			frappe.msgprint(
				f"Please wait {remaining} minute(s) before trying again to avoid Telegram rate limits.",
				title="Webhook Setup Cooldown"
			)
			return {"status": self.telegram_webhook_status}

		self._ensure_telegram_webhook_config()
		self._setup_telegram_webhook()
		return {"status": self.telegram_webhook_status}

	def _webhook_cooldown_remaining_minutes(self) -> int:
		"""Return remaining cooldown minutes, or 0 if none."""
		last_setup = self.telegram_last_webhook_setup
		if not last_setup:
			return 0
		try:
			remaining = (last_setup + timedelta(minutes=WEBHOOK_SETUP_COOLDOWN_MINUTES)) - now_datetime()
			return max(0, int(remaining.total_seconds() // 60))
		except Exception:
			return 0

	def _setup_telegram_webhook(self):
		"""Call Telegram setWebhook for this bot configuration.

		Uses raw DB updates and recursion flags to prevent repeated calls.
		"""
		if getattr(self, "flags", {}).get("in_telegram_webhook_setup"):
			frappe.log_error(
				f"Skipped recursive Telegram webhook setup for {self.name}",
				"Telegram Webhook"
			)
			return

		self.flags.in_telegram_webhook_setup = True
		status = ""
		reason = "auto" if not frappe.form_dict else "manual"

		# Re-generate URL if missing (e.g. get_url() was empty during an earlier save)
		if not self.telegram_webhook_url:
			self._ensure_telegram_webhook_config()

		webhook_url = self.telegram_webhook_url or ""
		if not webhook_url.startswith("https://"):
			status = "Failed: Webhook URL must use HTTPS (Telegram requirement)"
			if "localhost" in webhook_url or "127." in webhook_url:
				status += " and cannot be localhost"
			frappe.db.set_value(
				"Integration Settings", self.name, "telegram_webhook_status", status, update_modified=False
			)
			self.flags.in_telegram_webhook_setup = False
			frappe.log_error(
				f"Telegram webhook setup aborted for {self.name}: {status}",
				"Telegram Webhook"
			)
			return

		try:
			frappe.log_error(
				f"Starting Telegram webhook setup ({reason}) for {self.name}",
				"Telegram Webhook"
			)

			# Update timestamp with raw SQL to avoid triggering any document hooks
			frappe.db.set_value(
				"Integration Settings",
				self.name,
				"telegram_last_webhook_setup",
				now_datetime(),
				update_modified=False,
			)

			from huf.ai.tools.telegram import setup_webhook, get_webhook_info

			token = self.get_credential("token")
			if not token:
				status = "Failed: Telegram bot token not configured"
				frappe.db.set_value(
					"Integration Settings", self.name, "telegram_webhook_status", status, update_modified=False
				)
				return

			# Avoid setWebhook if already configured with the same URL
			webhook_info = get_webhook_info(token)
			info_ok = webhook_info.get("ok") or webhook_info.get("success")
			if info_ok:
				info_result = webhook_info.get("result") or webhook_info.get("results") or {}
				current_url = info_result.get("url", "")
				if current_url == self.telegram_webhook_url:
					pending = info_result.get("pending_update_count", 0)
					status = f"Webhook already configured ({pending} pending updates)"
					frappe.db.set_value(
						"Integration Settings", self.name, "telegram_webhook_status", status, update_modified=False
					)
					return

			result = setup_webhook(
				token=token,
				webhook_url=self.telegram_webhook_url,
				secret_token=self.get_password("telegram_webhook_secret"),
			)
			if not result.get("ok") and not result.get("success"):
				status = result.get("description") or result.get("error") or "Webhook setup failed"
			else:
				status = result.get("description") or "Webhook configured"
		except Exception as e:
			status = f"Failed: {str(e)[:120]}"
			frappe.log_error(f"Telegram webhook setup failed for {self.name}: {e}", "Telegram Webhook")
		finally:
			self.flags.in_telegram_webhook_setup = False
			if status:
				frappe.db.set_value(
					"Integration Settings", self.name, "telegram_webhook_status", status, update_modified=False
				)
			frappe.log_error(
				f"Finished Telegram webhook setup ({reason}) for {self.name}: {status}",
				"Telegram Webhook"
			)
