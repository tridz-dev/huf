"""Run budget primitives for deadline, depth, and spend cap enforcement."""

from datetime import datetime, timedelta
import frappe
from frappe.utils import get_datetime, cint, flt
from huf.ai.cost_calculator import get_model_pricing, _calculate_from_custom_pricing


class RunBudgetExceeded(frappe.ValidationError):
    """Raised when a run or its chain exceeds the configured deadline,
    recursion depth, or spend cap."""
    pass


class RunBudget:
    """Shared budget for a run and all child runs."""

    def __init__(self, deadline_at: datetime, max_turns_ceiling: int,
                 depth: int, ancestry: list, spend_cap_usd: float):
        self.deadline_at = deadline_at  # wall-clock deadline
        self.max_turns_ceiling = max_turns_ceiling  # int, server-enforced
        self.current_depth = depth  # current recursion depth
        self.ancestry = ancestry  # list of parent run IDs
        self.spend_cap_usd = spend_cap_usd  # cumulative cap for the chain
        self.spend_so_far_usd = 0.0  # updated as runs complete

    def is_deadline_exceeded(self) -> bool:
        """Check if wall-clock deadline has passed."""
        return datetime.now() > self.deadline_at

    def check_deadline(self):
        """Raise if deadline exceeded."""
        if self.is_deadline_exceeded():
            frappe.throw("Run budget deadline exceeded",
                       RunBudgetExceeded)

    def check_depth(self, max_depth: int = None):
        """Raise if recursion depth ceiling exceeded."""
        if max_depth is None:
            max_depth = cint(frappe.db.get_single_value("Agent Settings", "max_depth")) or 5
        if self.current_depth >= max_depth:
            frappe.throw(f"Recursion depth {self.current_depth} exceeds ceiling {max_depth}",
                       RunBudgetExceeded)

    def check_spend(self, estimated_cost_usd: float):
        """Raise if adding estimated cost would exceed cap. A cap of 0 means unlimited."""
        if not self.spend_cap_usd:
            return
        if self.spend_so_far_usd + estimated_cost_usd > self.spend_cap_usd:
            frappe.throw(f"Spend {estimated_cost_usd} exceeds remaining budget",
                       RunBudgetExceeded)

    @staticmethod
    def from_agent(agent_doc, parent_run_id: str = None,
                   deadline_secs: int = None) -> "RunBudget":
        """Create a RunBudget for a new run.

        ``parent_run_id`` names a row in the ``Agent Run`` doctype (the field
        on Agent Run itself is ``parent_run``, not ``parent_run_id`` —
        `huf/ai/agent_integration.py:1257`). Ancestry/depth are read from the
        ``budget_depth``/``budget_ancestry`` fields that ST-09.8 adds to
        Agent Run, not from fields named ``depth``/``ancestry`` (Agent Run
        has neither today).
        """
        if deadline_secs is None:
            deadline_secs = cint(frappe.db.get_single_value("Agent Settings",
                                            "deadline_seconds")) or 900
        settings_max_turns_ceiling = cint(frappe.db.get_single_value("Agent Settings",
                                            "max_turns_ceiling")) or 20
        max_turns = min(cint(agent_doc.max_turns) or 10, settings_max_turns_ceiling)
        # spend_cap_usd == 0 means unlimited (see ST-09.4); do not coalesce
        # a falsy site-wide value into a non-zero default — that inverts
        # "unlimited" into a hard cap (reviewer item 12).
        spend_cap = frappe.db.get_single_value("Agent Settings", "spend_cap_usd")
        spend_cap = flt(spend_cap) if spend_cap is not None else 0

        ancestry = []
        current_depth = 0
        if parent_run_id:
            parent_run = frappe.get_value("Agent Run", parent_run_id,
                                         ["budget_ancestry", "budget_depth"], as_dict=True)
            parent_ancestry = frappe.parse_json(parent_run.get("budget_ancestry")) if parent_run.get("budget_ancestry") else []
            ancestry = parent_ancestry + [parent_run_id]
            current_depth = (parent_run.get("budget_depth") or 0) + 1

        return RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=deadline_secs),
            max_turns_ceiling=max_turns,
            depth=current_depth,
            ancestry=ancestry,
            spend_cap_usd=spend_cap
        )

    @staticmethod
    def from_run_doc(run_doc) -> "RunBudget":
        """Rebuild a RunBudget from persisted fields on an Agent Run document.

        This reads the four budget fields added by ST-09.8:
        - budget_deadline_at (DateTime): the deadline when the run started
        - budget_depth (Int): the depth of this run in the chain
        - budget_ancestry (JSON): list of parent run IDs
        - budget_spend_usd (Float): actual spend for this run
        """
        deadline_at = run_doc.get("budget_deadline_at")
        if isinstance(deadline_at, str):
            deadline_at = get_datetime(deadline_at)

        ancestry = run_doc.get("budget_ancestry")
        if isinstance(ancestry, str):
            ancestry = frappe.parse_json(ancestry)
        if not ancestry:
            ancestry = []

        # Fetch settings for spend cap
        spend_cap = frappe.db.get_single_value("Agent Settings", "spend_cap_usd")
        spend_cap = flt(spend_cap) if spend_cap is not None else 0

        budget = RunBudget(
            deadline_at=deadline_at,
            max_turns_ceiling=10,  # fallback; read actual ceiling from settings if needed
            depth=run_doc.get("budget_depth") or 0,
            ancestry=ancestry,
            spend_cap_usd=spend_cap
        )
        budget.spend_so_far_usd = run_doc.get("budget_spend_usd") or 0.0
        return budget


def get_current_budget() -> RunBudget:
    """Get the current run's budget from the context var, or return a default.

    This is an in-process cache only and does not cross process boundaries.
    Callers that cross a process boundary must rebuild the budget from the
    persisted fields on the Agent Run document using RunBudget.from_run_doc().
    """
    # Import here to avoid circular import at module load time
    import contextvars

    # Define the context var at module level
    if not hasattr(get_current_budget, '_context_var'):
        get_current_budget._context_var = contextvars.ContextVar('huf_current_budget', default=None)

    budget = get_current_budget._context_var.get()
    if budget is None:
        # Return a default budget (depth 0, unlimited deadline/spend)
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=20,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
    return budget


def set_current_budget(budget: RunBudget):
    """Set the current run's budget in the context var.

    This is for in-process caching only within a single call stack.
    """
    import contextvars

    if not hasattr(get_current_budget, '_context_var'):
        get_current_budget._context_var = contextvars.ContextVar('huf_current_budget', default=None)

    get_current_budget._context_var.set(budget)


def estimate_run_cost(agent_doc, model: str = None, provider: str = None) -> float:
    """Estimate the cost of running an agent.

    Sums: input_tokens * input_price + output_tokens * output_price.
    Uses cached token counts from the agent's prompt and prior runs in the
    chain if available; falls back to a reasonable default estimate.

    Args:
        agent_doc: The Agent document
        model: Model name (defaults to agent_doc.model)
        provider: Provider name (defaults to agent_doc.provider)

    Returns:
        Estimated cost in USD
    """
    if model is None:
        model = agent_doc.model
    if provider is None:
        provider = agent_doc.provider

    if not model:
        # No model configured, cannot estimate
        return 0.0

    try:
        # Get pricing information for the model
        pricing = get_model_pricing(model)
        if not pricing:
            # No pricing available, fall back to conservative default estimate
            # Assume ~1000 input tokens and ~500 output tokens for a typical run
            # Use LiteLLM's auto-lookup if available, otherwise return 0
            try:
                from litellm import get_pricing
                litellm_pricing = get_pricing(model)
                if litellm_pricing and "input" in litellm_pricing and "output" in litellm_pricing:
                    input_price = litellm_pricing["input"]
                    output_price = litellm_pricing["output"]
                    # Default estimate: 1000 input, 500 output tokens
                    estimated_cost = (1000 / 1_000_000) * input_price + (500 / 1_000_000) * output_price
                    return max(0.0, estimated_cost)
            except Exception:
                pass
            # No pricing found, return 0
            return 0.0

        # Calculate using known pricing
        # Default estimate: 1000 input tokens, 500 output tokens
        input_tokens = 1000
        output_tokens = 500

        # Try to get more accurate estimates from prior runs if available
        # Look for recent Agent Run records with this agent and model
        try:
            prior_runs = frappe.db.get_list(
                "Agent Run",
                filters={
                    "agent": agent_doc.name,
                    "model": model,
                },
                fields=["input_tokens", "output_tokens"],
                order_by="creation desc",
                limit_page_length=5,
            )
            if prior_runs:
                # Average the last 5 runs
                avg_input = sum(r.get("input_tokens") or 0 for r in prior_runs) / len(prior_runs)
                avg_output = sum(r.get("output_tokens") or 0 for r in prior_runs) / len(prior_runs)
                if avg_input > 0:
                    input_tokens = int(avg_input)
                if avg_output > 0:
                    output_tokens = int(avg_output)
        except Exception:
            # If we can't get prior runs, just use defaults
            pass

        # Use the custom pricing to calculate cost
        estimated_cost = _calculate_from_custom_pricing(
            pricing,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return max(0.0, estimated_cost)
    except Exception as e:
        frappe.logger("huf").warning(f"Failed to estimate run cost for {model}: {str(e)}")
        return 0.0
