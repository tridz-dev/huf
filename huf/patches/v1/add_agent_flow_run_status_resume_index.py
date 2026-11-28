from huf.huf.doctype.agent_flow_run.agent_flow_run import on_doctype_update


def execute():
	"""Add the (status, resume_at) sweeper index on existing sites."""
	on_doctype_update()
