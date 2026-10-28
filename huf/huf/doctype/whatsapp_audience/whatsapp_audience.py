# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

PURPOSE_FIELDS = ("purpose_marketing", "purpose_utility", "purpose_events")


class WhatsAppAudience(Document):
	"""A consented list of WhatsApp contacts. Opt-out is NOT stored here: it stays in the gateway's
	consent records and is looked up when the list is used."""

	def validate(self):
		self.title = (self.title or "").strip()
		self.consent_source = (self.consent_source or "").strip()
		if not self.title:
			frappe.throw("An audience needs a title.")
		if not self.consent_source:
			frappe.throw("Say where consent for this list was collected.")
		if self.is_new():
			self._stamp_attestation()
		else:
			self._check_immutable()
			self._check_referenced_rename()

	def _stamp_attestation(self):
		# Always server-side: whatever the client sent is overwritten.
		self.consent_attested_by = frappe.session.user
		self.consent_attested_at = now_datetime()
		if self.default_consent_at and get_datetime(self.default_consent_at) > get_datetime(self.consent_attested_at):
			frappe.throw("The consent date cannot be in the future.")

	def _check_immutable(self):
		before = self.get_doc_before_save()
		if not before:
			return
		for field in ("consent_attested_by", "consent_attested_at", "default_consent_at", "gateway", "consent_basis"):
			if _norm(before.get(field)) != _norm(self.get(field)):
				frappe.throw(f"{self.meta.get_label(field)} cannot be changed after the audience is created.")
		for field in PURPOSE_FIELDS:
			if self.get(field) and not before.get(field):
				frappe.throw("Consent purposes can be narrowed but not widened. Create a new audience for a new purpose.")

	def _check_referenced_rename(self):
		before = self.get_doc_before_save()
		if before and before.title != self.title:
			from huf.ai.whatsapp.broadcast import audience as aud

			aud.assert_not_in_use(self.name, "renamed")

	def on_trash(self):
		from huf.ai.whatsapp.broadcast import audience as aud

		aud.assert_not_in_use(self.name, "deleted")
		frappe.flags.in_audience_api = True
		for name in frappe.get_all("WhatsApp Audience Member", {"audience": self.name}, pluck="name", limit_page_length=0):
			frappe.delete_doc("WhatsApp Audience Member", name, ignore_permissions=True, force=True)


def _norm(value):
	return "" if value in (None, "") else str(value)
