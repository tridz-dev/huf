"""Approval notifications for Human Approval steps (bell notification and email).

Split out of ``engine.py``; the engine imports both functions and calls them by its own global
names, so tests can still patch them on the engine module.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.desk.doctype.notification_settings.notification_settings import is_email_notifications_enabled

from huf.ai.transaction import commit_if_background



def _send_approval_notifications(flow_run, node: dict, config: dict, waiting_data: dict):
	"""
	Send notification to approvers when a flow reaches human.approval node.
	
	Supports two notification methods:
	1. Frappe Notification Log (bell icon in UI)
	2. Email notification (if email is configured)
	
	Args:
		flow_run: The Flow Run document
		node: The current node dict
		config: Node configuration
		waiting_data: The waiting state data
	"""
	approver_type = waiting_data.get("approver_type")
	approvers = []

	# Same rule as check_approver: no declared approver means System Manager only.
	if approver_type == "role" and waiting_data.get("approver_role"):
		approver_role = waiting_data.get("approver_role")
	elif approver_type == "user" and waiting_data.get("approver_users"):
		approver_role = None
	else:
		approver_type, approver_role = "role", "System Manager"

	if approver_type == "role":
		if approver_role:
			# Optimized role lookup: Get all users with this role directly from Has Role table
			approver_names = frappe.get_all(
				"Has Role",
				filters={"role": approver_role, "parenttype": "User"},
				pluck="parent"
			)
			if approver_names:
				# Filter to ensure we only notify enabled System Users
				approvers = frappe.get_all(
					"User",
					filters={
						"name": ["in", approver_names],
						"enabled": 1,
						"user_type": "System User",
					},
					pluck="name"
				)
	elif approver_type == "user":
		approvers = list(waiting_data.get("approver_users") or [])
	
	# Ensure unique recipients to avoid duplicate emails
	if approvers:
		approvers = list(set(approvers))
	
	if not approvers:
		frappe.log_error(
			title="Flow Approval Notification",
			message=f"No approvers found for flow run {flow_run.name}",
		)
		return
	
	title = "Approval Required"
	instructions = waiting_data.get("message") or "Please review and approve this flow."
	
	flow_run_path = f"/huf/flows/{flow_run.flow_id}?run={flow_run.name}"
	
	_host = (frappe.conf.get("host_name") or frappe.utils.get_url()).rstrip("/")
	flow_run_url = f"{_host}{flow_run_path}"

	
	# Create notification for each approver
	for user in approvers:
		try:
			# Get user email for notification (enqueue_create_notification expects emails)
			user_email = frappe.db.get_value("User", user, "email") or user
			
			# 1. Create Frappe Notification Log (appears in bell icon)
			enqueue_create_notification(user_email, {
				"type": "Assignment",
				"document_type": "Flow Run",
				"document_name": flow_run.name,
				"subject": _("Approval Required: {0}").format(title),
				"email_content": f"""
					<p>{instructions}</p>
					<p><strong>{_("Flow")}:</strong> {flow_run.flow_id}</p>
					<p><strong>{_("Run ID")}:</strong> {flow_run.name}</p>
					<p><a href="{flow_run_url}">{_("View Flow Run")}</a></p>
				""",
			})
			
			if is_email_notifications_enabled(user):
				user_doc = frappe.get_doc("User", user)
				if user_doc.email:
					frappe.sendmail(
						recipients=[user_doc.email],
						subject=_("[HUF] Approval Required: {0}").format(title),
						message=f"""
							<p>{_("Dear")} {user_doc.full_name or user},</p>
							<p>{_("A flow is waiting for your approval.")}</p>
							<hr>
							<p><strong>{_("Flow")}:</strong> {flow_run.flow_id}</p>
							<p><strong>{_("Run ID")}:</strong> {flow_run.name}</p>
							<p><strong>{_("Instructions")}:</strong></p>
							<p>{instructions}</p>
							<hr>
							<p>
								<a href="{flow_run_url}" 
								   style="background-color: #171717; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
									{_("Review Approval")}
								</a>
							</p>
							<p style="color: #666; font-size: 12px;">
								{_("This is an automated message from the HUF Flow Engine.")}
							</p>
						""",
						delayed=True,
					)
		except Exception as e:
			# Log error but don't fail the flow
			frappe.log_error(
				title=_("Flow Approval Notification"),
				message=f"Failed to send approval notification to {user}: {str(e)}",
			)


def _clear_flow_notifications(flow_run):
	"""
	Mark all notifications for a specific flow run as read.
	Called when a human decision is made.

	Best effort, and it must run AFTER the decision has been committed: the notification rows may be
	inserted by a background job at the same moment, and a conflicting write (MariaDB snapshot conflict
	1020 or a deadlock) rolls back the whole open transaction, not just this statement. A failed attempt
	is retried once on a fresh transaction; after that the notifications stay unread (a log line says so).
	"""
	for attempt in (1, 2):
		try:
			# Standard Frappe approach: find notification log entries for this document
			# and mark them as read for all users who were notified.
			frappe.db.set_value(
				"Notification Log",
				{
					"document_type": "Flow Run",
					"document_name": flow_run.name,
					"read": 0
				},
				"read",
				1,
				update_modified=False
			)
			commit_if_background()
			return
		except Exception as exc:
			if attempt == 1 and isinstance(exc, frappe.QueryDeadlockError):
				frappe.db.rollback()  # the database already ended the transaction; start a clean one
				continue
			frappe.logger("huf").warning(f"Could not mark the approval notifications of run {flow_run.name} as read: {exc}")
			return
