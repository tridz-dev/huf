"""Indexes supporting the scheduled Agent Run analytics rollup."""

import frappe


def _add_index(doctype, fields, name, unique=False):
    try:
        if unique:
            frappe.db.add_unique(doctype, fields, name)
        else:
            frappe.db.add_index(doctype, fields, name)
    except Exception as error:
        # A previously deployed/manual index must not make migrate fail.
        if "Duplicate key name" not in str(error):
            raise


def execute():
    if frappe.db.has_column("Agent Run", "start_time"):
        _add_index("Agent Run", ["start_time", "status"], "idx_agent_run_analytics_time_status")
        _add_index("Agent Run", ["agent", "start_time"], "idx_agent_run_analytics_agent_time")
        _add_index("Agent Run", ["provider", "model", "start_time"], "idx_agent_run_analytics_model_time")

    if frappe.db.has_column("Agent Run Analytics Rollup", "bucket_start"):
        _add_index(
            "Agent Run Analytics Rollup",
            ["granularity", "bucket_start", "dimension_key"],
            "idx_agent_run_rollup_unique",
            unique=True,
        )
        _add_index(
            "Agent Run Analytics Rollup",
            ["granularity", "bucket_start"],
            "idx_agent_run_rollup_window",
        )
