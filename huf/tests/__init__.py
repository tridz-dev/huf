"""
HUF Flow Engine Test Suite

This package contains comprehensive tests for the HUF Flow Engine.

Test Categories:
- test_flow_engine.py: Unit tests for core flow engine functionality
- test_flow_api.py: API endpoint tests
- test_human_approval.py: Human approval workflow tests
- test_context.py: Context passing and interpolation tests

Usage:
    cd /workspace/development/edge16
    bench --site huf.localhost run-tests --app huf
"""

from frappe.tests.utils import FrappeTestCase


class TestFlowBase(FrappeTestCase):
    """Base class for all flow tests with common utilities."""
    
    def assertFlowRunStatus(self, flow_run_name: str, expected_status: str):
        """Assert that a flow run has the expected status."""
        import frappe
        flow_run = frappe.get_doc("Flow Run", flow_run_name)
        self.assertEqual(
            flow_run.status, 
            expected_status,
            f"Flow run {flow_run_name} expected status '{expected_status}' but got '{flow_run.status}'"
        )
    
    def assertFlowRunCompleted(self, flow_run_name: str):
        """Assert that a flow run completed successfully."""
        self.assertFlowRunStatus(flow_run_name, "Success")
    
    def assertFlowRunFailed(self, flow_run_name: str, expected_error: str | None = None):
        """Assert that a flow run failed with optional error message check."""
        import frappe
        flow_run = frappe.get_doc("Flow Run", flow_run_name)
        self.assertEqual(flow_run.status, "Failed")
        if expected_error:
            self.assertIn(expected_error, flow_run.last_error or "")


# Make all test classes available
from .test_flow_engine import TestFlowEngine
from .test_flow_api import TestFlowAPI
from .test_human_approval import TestHumanApproval
from .test_context import TestContextPassing

__all__ = [
    "TestFlowBase",
    "TestFlowEngine",
    "TestFlowAPI",
    "TestHumanApproval",
    "TestContextPassing",
]
