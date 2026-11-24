"""``member.set`` node: save values on the person this run is about, kept across runs (no expiry).

Config: ``vars`` (object of name -> value or reference). Read later as ``member.vars.<name>``.
Output ``{"saved": [names]}``.
"""

from __future__ import annotations

from huf.ai.flow import member as flow_member


def exec_member_set(flow_run, node: dict, config: dict, context) -> dict:
	extra = sorted(set(config) - {"vars"})
	if extra or not isinstance(config.get("vars"), dict) or not config["vars"]:
		return {"status": "failed", "error": "Choose the values to save for this person."}
	key = getattr(flow_run, "member_key", None)
	if not key:
		return {"status": "failed", "error": "This run does not know who it is about, so it cannot save anything for them."}
	flow = flow_run.flow_id
	values = {name: context.resolve(value) for name, value in config["vars"].items()}
	try:
		merged = flow_member.set_vars(flow, key, values)
	except flow_member.FlowMemberError as exc:
		return {"status": "failed", "error": str(exc)}
	flow_member.record_history(flow, key, node.get("id") or "", flow_run.name)
	if context.member is not None:
		context.member["vars"] = merged
	output = {"saved": sorted(values)}
	return {"status": "success", "result": output, "output": output}
