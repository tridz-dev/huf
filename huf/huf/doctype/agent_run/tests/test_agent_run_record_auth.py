"""Test record-level authorization for Agent Run doctype.

Tests the has_permission hook for Agent Run, verifying that only
the run owner, System Manager, or users with agent.view_all can
access a run.
"""

import frappe
import pytest


def test_agent_run_owner_can_read():
	"""Owner of a run can read it."""
	# Create a test run owned by alice
	run_doc = frappe.new_doc("Agent Run")
	run_doc.agent = "Test Agent"
	run_doc.status = "Success"
	run_doc.owner = "alice@example.com"
	run_doc.insert()

	try:
		# Verify alice can read it
		from huf.ai.record_access import user_can_read_run
		assert user_can_read_run(run_doc, user="alice@example.com") is True
	finally:
		run_doc.delete()


def test_agent_run_non_owner_cannot_read():
	"""Non-owner cannot read a run."""
	# Create a test run owned by alice
	run_doc = frappe.new_doc("Agent Run")
	run_doc.agent = "Test Agent"
	run_doc.status = "Success"
	run_doc.owner = "alice@example.com"
	run_doc.insert()

	try:
		# Verify bob cannot read it
		from huf.ai.record_access import user_can_read_run
		assert user_can_read_run(run_doc, user="bob@example.com") is False
	finally:
		run_doc.delete()


def test_agent_run_system_manager_can_read():
	"""System Manager can read any run."""
	# Create a test run owned by alice
	run_doc = frappe.new_doc("Agent Run")
	run_doc.agent = "Test Agent"
	run_doc.status = "Success"
	run_doc.owner = "alice@example.com"
	run_doc.insert()

	try:
		# Verify System Manager can read it
		from huf.ai.record_access import user_can_read_run
		assert user_can_read_run(run_doc, user="Administrator") is True
	finally:
		run_doc.delete()
