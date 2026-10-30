"""Shared shaping for the Flow Run endpoints (``get_flow_run``, ``list_flow_runs*``, ``get_pending_approvals``)."""

from __future__ import annotations

# The columns every Flow Run list needs (the Executions page, a flow's history, an agent tool's listing).
RUN_LIST_FIELDS = [
	"name",
	"flow_id",
	"flow_version",
	"mode",
	"run_mode",
	"status",
	"current_node_id",
	"hop_count",
	"trigger_type",
	"started_at",
	"completed_at",
	"modified",
]
