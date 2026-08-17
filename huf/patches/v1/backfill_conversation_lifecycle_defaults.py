import frappe


def execute():
	"""Backfill conversation_retention_policy / trash_retention_days on Agent rows created
	before the conversation-lifecycle fields existed, and status on pre-existing Agent
	Conversation rows. Select-field defaults only apply to new docs, so without this,
	every lifecycle action (hide/archive/trash/delete) would be denied for existing agents."""
	frappe.db.sql(
		"""
		UPDATE `tabAgent`
		SET conversation_retention_policy = 'allow_trash'
		WHERE conversation_retention_policy IS NULL OR conversation_retention_policy = ''
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabAgent`
		SET trash_retention_days = 30
		WHERE trash_retention_days IS NULL
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabAgent`
		SET message_retention_days = -1
		WHERE message_retention_days IS NULL
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabAgent Conversation`
		SET status = 'Active'
		WHERE status IS NULL OR status = ''
		"""
	)
	frappe.db.commit()
