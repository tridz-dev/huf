"""``router.llm`` node execution: let a model pick one of the configured paths.

Moved out of ``huf.ai.flow.engine`` unchanged; ``engine`` re-exports these names. Engine internals (and the router
helpers tests patch on ``engine``) are reached through a function-level ``from huf.ai.flow import engine`` to avoid
an import cycle.
"""


def _exec_router_llm(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute router.llm node (config: ``prompt``, ``options[{label,node_id}]``, ``default``, ``model``).

	The model picks an option by label; no match, an unusable reply, or any failure routes to
	``default`` (required, so routing is total). ``model`` is an optional AI Model name; absent means
	the first keyed provider's default chat model. Output is
	``{"label", "node_id", "reason", "model", "provider"}`` (``model`` is the one used, or attempted).
	"""
	from huf.ai.flow import engine

	options = [o for o in (config.get("options") or []) if isinstance(o, dict) and o.get("node_id")]
	default = config.get("default")
	if not default:
		return {"status": "failed", "error": "Choose which path to take when the AI cannot decide, then run again."}
	if not options:
		return {"status": "failed", "error": "Add at least one path for the AI to choose from, then run again."}

	blocked = _router_llm_ai_block(engine._run_context(settings))
	if blocked:
		return blocked
	ctx = engine._context_of(flow_run, settings)
	chosen, reason = None, ""
	provider, model = None, config.get("model") or None
	try:
		provider, model = engine.resolve_router_model(model)
		reply = engine._router_completion(
			engine.build_router_llm_prompt(
				engine.render_text_refs(config.get("prompt") or "", ctx),
				options,
				{"input": ctx.as_dict(), "steps": ctx.node_outputs},
			),
			provider,
			model,
		)
		if not reply:
			reason = "The AI did not answer, so the default path was taken."
		else:
			chosen = engine.choose_option(reply, options)
			reason = "matched" if chosen else "The answer did not match any path, so the default path was taken."
	except Exception as e:
		reason = f"The AI could not be asked, so the default path was taken. {engine.describe_exception(e)}"

	if chosen:
		node_id, label = chosen["node_id"], chosen.get("label")
	else:
		node_id, label = default, "default"
	return {
		"status": "success",
		"next_node_id": node_id,
		"output": {"label": label, "node_id": node_id, "reason": reason, "model": model, "provider": provider},
	}


def _router_llm_ai_block(run_ctx) -> dict | None:
	"""A failed result when the AI switch is off, the run's deadline passed or its spend cap is used up, else None.

	Checked before any provider is asked, so a switched-off site never reaches a model (H-W5-05).
	"""
	from huf.ai.run_budget import AI_DISABLED, AIDisabled, RunBudgetExceeded, assert_ai_enabled

	try:
		assert_ai_enabled(getattr(run_ctx, "agent", None))
		budget = getattr(run_ctx, "budget", None)
		if budget is not None:
			budget.check_deadline()
			if budget.spend_cap_usd and budget.spend_so_far_usd >= budget.spend_cap_usd:
				raise RunBudgetExceeded("spend cap reached")
			budget.check_spend(0.0)
	except AIDisabled:
		return {
			"status": "failed",
			"reason_code": AI_DISABLED,
			"error": "AI features are switched off on this site, so this step did not run.",
		}
	except RunBudgetExceeded:
		return {
			"status": "failed",
			"reason_code": "ai_budget_exceeded",
			"error": "This run has used up its AI budget, so this step did not run.",
		}
	except Exception:  # noqa: BLE001 - a kill switch must not fail open
		return {
			"status": "failed",
			"reason_code": AI_DISABLED,
			"error": "AI features could not be checked, so this step did not run.",
		}
	return None
