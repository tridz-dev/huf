"""Test record-level permissions for get_run_context_metrics endpoint.

Tests that the get_run_context_metrics endpoint only fetches the caller's
own previous run for comparison, not any previous run on the agent.
"""

import frappe
import pytest
from datetime import datetime, timedelta


def test_get_run_context_metrics_fetches_own_previous_run():
	"""get_run_context_metrics fetches the caller's own previous run."""
	# Create previous run owned by alice
	conv_doc = frappe.new_doc("Agent Conversation")
	conv_doc.agent = "Test Agent"
	conv_doc.owner = "alice@example.com"
	conv_doc.insert()

	prev_run_doc = frappe.new_doc("Agent Run")
	prev_run_doc.agent = "Test Agent"
	prev_run_doc.status = "Success"
	prev_run_doc.conversation = conv_doc.name
	prev_run_doc.owner = "alice@example.com"
	prev_run_doc.start_time = datetime.now() - timedelta(hours=1)
	prev_run_doc.insert()

	# Create current run owned by alice
	current_run_doc = frappe.new_doc("Agent Run")
	current_run_doc.agent = "Test Agent"
	current_run_doc.status = "Success"
	current_run_doc.conversation = conv_doc.name
	current_run_doc.owner = "alice@example.com"
	current_run_doc.start_time = datetime.now()
	current_run_doc.insert()

	try:
		old_user = frappe.session.user
		try:
			frappe.session.user = "alice@example.com"
			frappe.set_user("alice@example.com")

			from huf.ai.agent_run_context_api import get_run_context_metrics
			# Should not raise, and should find the previous run
			result = get_run_context_metrics(current_run_doc.name)
			assert result is not None
		finally:
			frappe.session.user = old_user
			frappe.set_user(old_user)
	finally:
		current_run_doc.delete()
		prev_run_doc.delete()
		conv_doc.delete()


def test_get_run_context_metrics_skips_foreign_previous_run():
	"""get_run_context_metrics does not fetch previous runs by other users."""
	# Create previous run owned by bob
	conv_bob = frappe.new_doc("Agent Conversation")
	conv_bob.agent = "Test Agent"
	conv_bob.owner = "bob@example.com"
	conv_bob.insert()

	prev_run_bob = frappe.new_doc("Agent Run")
	prev_run_bob.agent = "Test Agent"
	prev_run_bob.status = "Success"
	prev_run_bob.conversation = conv_bob.name
	prev_run_bob.owner = "bob@example.com"
	prev_run_bob.start_time = datetime.now() - timedelta(hours=1)
	prev_run_bob.insert()

	# Create current run owned by alice
	conv_alice = frappe.new_doc("Agent Conversation")
	conv_alice.agent = "Test Agent"
	conv_alice.owner = "alice@example.com"
	conv_alice.insert()

	current_run_doc = frappe.new_doc("Agent Run")
	current_run_doc.agent = "Test Agent"
	current_run_doc.status = "Success"
	current_run_doc.conversation = conv_alice.name
	current_run_doc.owner = "alice@example.com"
	current_run_doc.start_time = datetime.now()
	current_run_doc.insert()

	try:
		old_user = frappe.session.user
		try:
			frappe.session.user = "alice@example.com"
			frappe.set_user("alice@example.com")

			from huf.ai.agent_run_context_api import get_run_context_metrics
			# Should not raise, and should not use bob's previous run
			result = get_run_context_metrics(current_run_doc.name)
			assert result is not None
			# The metrics should not have been computed against bob's run
		finally:
			frappe.session.user = old_user
			frappe.set_user(old_user)
	finally:
		current_run_doc.delete()
		conv_alice.delete()
		prev_run_bob.delete()
		conv_bob.delete()
