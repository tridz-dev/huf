# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Frappe-free in-memory workloads for the safe-deopt experiment (Track-Item: 3).

Two workloads, both pure Python -- importable and runnable under plain ``pytest``, no
bench, no frappe import anywhere in this module. They mirror the shapes of
``huf/ai/tests/test_benchmark3_write_runtime.py`` (W1, CRM follow-up) and
``huf/ai/tests/test_procedure_runtime_benchmark4.py`` (W2, payment allocation), but are
deliberately standalone: this module does not import ``huf.ai.graph.procedure_runtime`` or
``huf.ai.graph.idempotency`` at all, since the point of the safe-deopt experiment is to run
these stores *underneath* a fault-injecting tool-invoker layer that a later harness will
build independently of the real procedure runtime.

Core design requirement (this is the whole point of the experiment): every store keeps an
APPEND-ONLY COMMIT LOG (``CommitLogEntry`` rows in ``.commit_log``) that records the TRUE
outcome of every write attempt -- committed or not -- independent of and invisible to
whatever a tool-invoker wrapper reports back to its caller. A fault-injection layer wrapping
these stores can freely lie about the return value it hands to an agent (e.g. claim
"timeout" when the store in fact committed the row), but it cannot touch ``.commit_log`` --
that list is the ground truth a grading harness reads to check what *actually* happened,
independent of what the agent was told.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
	"CommitLogEntry",
	"Authorizer",
	"allow_all",
	"PermissionDenied",
	# W1
	"Customer",
	"OpenItem",
	"ToDo",
	"CrmStore",
	# W2
	"Invoice",
	"Payment",
	"Allocation",
	"PaymentAllocationStore",
	"classify_payment",
	# W3
	"Account",
	"PriorOrder",
	"DraftOrder",
	"OrderProcessingStore",
	"EligibilityDenied",
	"check_eligibility",
	"compute_pricing",
]


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class PermissionDenied(RuntimeError):
	"""Raised by a store when its authorizer hook refuses a write."""


# An authorizer is given (action_name, payload) and returns True iff the write may proceed.
# Defaults to "always allowed" everywhere below; the authority sub-experiment overrides this
# per-store to test that no write ever exceeds the invoker's actual permissions.
Authorizer = Callable[[str, dict], bool]


def allow_all(_action: str, _payload: dict) -> bool:
	return True


@dataclass
class CommitLogEntry:
	"""One append-only record of a write ATTEMPT's true outcome.

	This is ground truth: written by the store itself, at the moment a write is attempted,
	before any fault-injection wrapper gets a chance to intercept or rewrite the response
	handed back to the caller. ``seq`` is a strictly increasing, per-store attempt counter
	(not a timestamp) so ordering is deterministic and comparable across a test run.
	"""

	seq: int
	action: str  # e.g. "create_followup_todo", "submit_allocation"
	operation_key: str  # the logical write's dedup/audit key (see each store's docstring)
	committed: bool  # True iff the underlying record store was actually mutated
	record_key: str | None  # the identity of the record written/touched, if committed
	detail: dict = field(default_factory=dict)


class _CommitLogMixin:
	"""Shared append-only commit-log bookkeeping for both stores."""

	def _init_log(self) -> None:
		self.commit_log: list[CommitLogEntry] = []
		self._seq = itertools.count(1)

	def _record(self, *, action: str, operation_key: str, committed: bool, record_key: str | None, **detail: Any) -> CommitLogEntry:
		entry = CommitLogEntry(
			seq=next(self._seq),
			action=action,
			operation_key=operation_key,
			committed=committed,
			record_key=record_key,
			detail=dict(detail),
		)
		self.commit_log.append(entry)
		return entry

	def committed_keys_for(self, action: str) -> list[str]:
		"""All record keys committed under ``action``, per the ground-truth log."""
		return [e.record_key for e in self.commit_log if e.action == action and e.committed and e.record_key]


# ---------------------------------------------------------------------------
# W1 -- CRM follow-up (benchmark-3 shape)
# ---------------------------------------------------------------------------


@dataclass
class Customer:
	customer_id: str
	name: str
	company: str


@dataclass
class OpenItem:
	reference_type: str  # e.g. "Sales Invoice"
	reference_name: str  # e.g. "SINV-2001"
	customer_id: str
	outstanding_amount: float
	status: str = "open"  # "open" | "submitted"


@dataclass
class ToDo:
	name: str
	reference_type: str
	reference_name: str
	allocated_to: str
	operation_key: str
	description: str = ""


class CrmStore(_CommitLogMixin):
	"""In-memory stand-in for the ERPNext ``ToDo`` + linked-document world benchmark-3 acts on.

	Reads
	-----
	``read_customer`` / ``read_open_items`` never write and are never logged.

	Writes
	------
	- ``create_followup_todo`` (write A): creates a ``ToDo``-like record. Takes an explicit
	  ``operation_key`` (mirrors ``huf.ai.graph.idempotency.derive_operation_key``'s shape --
	  "procedure:node:target" -- but this module does not import that code, it only mirrors
	  the convention). A second call with the SAME ``operation_key`` is a no-op: it returns
	  the existing ``ToDo`` and does NOT append a second ``committed=True`` entry for a new
	  record, matching benchmark-3's own "a retry cannot create a duplicate ToDo" invariant.
	- ``update_linked_record`` / ``submit_linked_record`` (write B): mutates the linked
	  ``OpenItem``'s status. Submission is idempotent by construction: submitting an
	  already-submitted item is a no-op that still logs an attempt (so the ground truth shows
	  the invoker was called), but does not flip state twice.

	Pending / non-critical
	-----------------------
	- ``notify`` is modeled as a side channel: it is logged in ``self.pending_notifications``,
	  not in ``commit_log`` (it is not a record write), and a task is allowed to be graded
	  "complete" whether or not notify ever fires.
	"""

	def __init__(self, *, authorizer: Authorizer = allow_all):
		self._init_log()
		self.authorizer = authorizer
		self.customers: dict[str, Customer] = {}
		self.open_items: dict[tuple[str, str], OpenItem] = {}
		self.todos: dict[str, ToDo] = {}
		self._todos_by_operation_key: dict[str, str] = {}
		self._todo_counter = itertools.count(1)
		self.pending_notifications: list[dict] = []

	# -- seeding -----------------------------------------------------------

	def seed_customer(self, customer: Customer) -> None:
		self.customers[customer.customer_id] = customer

	def seed_open_item(self, item: OpenItem) -> None:
		self.open_items[(item.reference_type, item.reference_name)] = item

	# -- reads ---------------------------------------------------------------

	def read_customer(self, customer_id: str) -> Customer | None:
		return self.customers.get(customer_id)

	def read_open_items(self, customer_id: str) -> list[OpenItem]:
		return [item for item in self.open_items.values() if item.customer_id == customer_id and item.status == "open"]

	# -- write A ---------------------------------------------------------------

	def create_followup_todo(
		self, *, reference_type: str, reference_name: str, allocated_to: str, operation_key: str, description: str = ""
	) -> ToDo:
		"""Idempotent by ``operation_key``: a duplicate call returns the same record."""
		existing_name = self._todos_by_operation_key.get(operation_key)
		if existing_name is not None:
			self._record(
				action="create_followup_todo",
				operation_key=operation_key,
				committed=False,
				record_key=existing_name,
				reason="duplicate_operation_key",
			)
			return self.todos[existing_name]

		if not self.authorizer("create_followup_todo", {"reference_type": reference_type, "reference_name": reference_name}):
			self._record(action="create_followup_todo", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"create_followup_todo denied for {reference_type}:{reference_name}")

		name = f"TODO-{next(self._todo_counter):04d}"
		todo = ToDo(
			name=name,
			reference_type=reference_type,
			reference_name=reference_name,
			allocated_to=allocated_to,
			operation_key=operation_key,
			description=description,
		)
		self.todos[name] = todo
		self._todos_by_operation_key[operation_key] = name
		self._record(action="create_followup_todo", operation_key=operation_key, committed=True, record_key=name)
		return todo

	# -- write B ---------------------------------------------------------------

	def submit_linked_record(self, *, reference_type: str, reference_name: str, operation_key: str) -> OpenItem:
		"""Submits (or updates the status of) the linked ``OpenItem``. Idempotent: submitting
		an already-submitted record logs the attempt but does not double-submit.
		"""
		key = (reference_type, reference_name)
		item = self.open_items.get(key)
		if item is None:
			self._record(action="submit_linked_record", operation_key=operation_key, committed=False, record_key=None, reason="not_found")
			raise KeyError(f"no such open item {reference_type}:{reference_name}")

		record_key = f"{reference_type}:{reference_name}"
		if item.status == "submitted":
			self._record(action="submit_linked_record", operation_key=operation_key, committed=False, record_key=record_key, reason="already_submitted")
			return item

		if not self.authorizer("submit_linked_record", {"reference_type": reference_type, "reference_name": reference_name}):
			self._record(action="submit_linked_record", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"submit_linked_record denied for {record_key}")

		item.status = "submitted"
		self._record(action="submit_linked_record", operation_key=operation_key, committed=True, record_key=record_key)
		return item

	# alias matching the task brief's alternate name for write B
	update_linked_record = submit_linked_record

	# -- pending / non-critical -----------------------------------------------

	def notify(self, *, channel: str, message: str) -> None:
		"""Non-critical side channel. Never appended to ``commit_log`` -- a task can be
		graded complete whether or not this ever fires, and a fault-injection wrapper is
		free to drop this call entirely without affecting ground truth.
		"""
		self.pending_notifications.append({"channel": channel, "message": message})


# ---------------------------------------------------------------------------
# W2 -- payment allocation (benchmark-4 shape, extended)
# ---------------------------------------------------------------------------


@dataclass
class Invoice:
	name: str
	customer: str
	outstanding_amount: float
	company: str = "Huf Retail Pvt Ltd"


@dataclass
class Payment:
	name: str
	customer: str
	amount: float
	company: str = "Huf Retail Pvt Ltd"
	reference: str | None = None  # e.g. bank reference; used for exact reference matching


@dataclass
class Allocation:
	name: str
	payment: str
	invoice: str
	amount: float
	operation_key: str
	status: str = "draft"  # "draft" | "submitted"


def classify_payment(payment: Payment, invoices: list[Invoice]) -> dict:
	"""Classification mirrors ``test_procedure_runtime_benchmark4.py``'s ``_classify_payment``:
	a single invoice with the same amount (within cents) for the same customer is a unique
	resolved match; an exact reference+amount match is also resolved; anything else (no
	match, or multiple equally-good candidates) is ``needs_review``.

	Returns ``{"payment": name, "classification": "resolved"|"needs_review", "invoice":
	name|None, "candidates": [...]}``.
	"""
	same_customer = [inv for inv in invoices if inv.customer == payment.customer]

	# Exact reference match (if the payment carries one) is the strongest signal.
	if payment.reference:
		ref_matches = [inv for inv in same_customer if inv.name == payment.reference]
		if len(ref_matches) == 1 and abs(ref_matches[0].outstanding_amount - payment.amount) < 0.01:
			return {"payment": payment.name, "classification": "resolved", "invoice": ref_matches[0].name, "candidates": [ref_matches[0].name]}

	amount_matches = [inv for inv in same_customer if abs(inv.outstanding_amount - payment.amount) < 0.01]
	if len(amount_matches) == 1:
		return {"payment": payment.name, "classification": "resolved", "invoice": amount_matches[0].name, "candidates": [amount_matches[0].name]}

	return {
		"payment": payment.name,
		"classification": "needs_review",
		"invoice": None,
		"candidates": [inv.name for inv in amount_matches],
	}


class PaymentAllocationStore(_CommitLogMixin):
	"""In-memory stand-in for the reconciliation world benchmark-4 acts on.

	Reads
	-----
	``list_invoices`` / ``list_payments`` never write.

	Writes
	------
	- ``create_allocation`` (write A): creates a draft ``Allocation`` row. Idempotent by an
	  explicit ``operation_key``, distinct from write B's key (per the task brief: "explicit
	  operation key, distinct from write B").
	- ``submit_allocation`` (write B, idempotent variant): submits a draft allocation and
	  decrements the invoice's outstanding amount. Idempotent by ``operation_key`` -- a
	  duplicate call is a no-op that does not double-decrement the invoice.
	- ``submit_allocation_unsafe`` (write B, NON-idempotent variant): same effect as
	  ``submit_allocation`` but with NO idempotency-key parameter and NO existing-check
	  performed before writing. Every call unconditionally creates a brand-new submitted
	  allocation and decrements the invoice again. This exists specifically so that, later,
	  the UNKNOWN-outcome case (agent unsure whether its write landed) cannot be "solved" by
	  blind replay -- replaying against this variant produces a real duplicate.

	Pending / non-critical
	-----------------------
	- ``update_followup_status`` is modeled as a side channel (e.g. updating a CRM follow-up
	  task's status once a payment is reconciled) -- logged separately from ``commit_log``,
	  can be left pending without failing the task.
	"""

	def __init__(self, *, authorizer: Authorizer = allow_all):
		self._init_log()
		self.authorizer = authorizer
		self.invoices: dict[str, Invoice] = {}
		self.payments: dict[str, Payment] = {}
		self.allocations: dict[str, Allocation] = {}
		self._allocations_by_operation_key: dict[str, str] = {}
		self._submitted_operation_keys: set[str] = set()
		self._allocation_counter = itertools.count(1)
		self.pending_followup_updates: list[dict] = []

	# -- seeding -----------------------------------------------------------

	def seed_invoice(self, invoice: Invoice) -> None:
		self.invoices[invoice.name] = invoice

	def seed_payment(self, payment: Payment) -> None:
		self.payments[payment.name] = payment

	# -- reads ---------------------------------------------------------------

	def list_invoices(self) -> list[Invoice]:
		return list(self.invoices.values())

	def list_payments(self) -> list[Payment]:
		return list(self.payments.values())

	# -- write A ---------------------------------------------------------------

	def create_allocation(self, *, payment: str, invoice: str, amount: float, operation_key: str) -> Allocation:
		existing_name = self._allocations_by_operation_key.get(operation_key)
		if existing_name is not None:
			self._record(
				action="create_allocation", operation_key=operation_key, committed=False, record_key=existing_name, reason="duplicate_operation_key"
			)
			return self.allocations[existing_name]

		if not self.authorizer("create_allocation", {"payment": payment, "invoice": invoice, "amount": amount}):
			self._record(action="create_allocation", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"create_allocation denied for {payment}->{invoice}")

		name = f"ALLOC-{next(self._allocation_counter):04d}"
		row = Allocation(name=name, payment=payment, invoice=invoice, amount=amount, operation_key=operation_key)
		self.allocations[name] = row
		self._allocations_by_operation_key[operation_key] = name
		self._record(action="create_allocation", operation_key=operation_key, committed=True, record_key=name)
		return row

	# -- write B (idempotent variant) -------------------------------------------

	def submit_allocation(self, *, allocation: str, operation_key: str) -> Allocation:
		"""Idempotent submit: a duplicate call with the same ``operation_key`` (distinct
		namespace from write A's keys) is a logged no-op, and the invoice is decremented
		exactly once.
		"""
		row = self.allocations.get(allocation)
		if row is None:
			self._record(action="submit_allocation", operation_key=operation_key, committed=False, record_key=None, reason="not_found")
			raise KeyError(f"no such allocation {allocation}")

		if operation_key in self._submitted_operation_keys:
			self._record(action="submit_allocation", operation_key=operation_key, committed=False, record_key=allocation, reason="duplicate_operation_key")
			return row

		if row.status == "submitted":
			# Reached via a different-but-equivalent operation_key than the one that already
			# submitted it -- still must not double-decrement.
			self._record(action="submit_allocation", operation_key=operation_key, committed=False, record_key=allocation, reason="already_submitted")
			return row

		if not self.authorizer("submit_allocation", {"allocation": allocation}):
			self._record(action="submit_allocation", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"submit_allocation denied for {allocation}")

		invoice = self.invoices.get(row.invoice)
		if invoice is not None:
			invoice.outstanding_amount -= row.amount
		row.status = "submitted"
		self._submitted_operation_keys.add(operation_key)
		self._record(action="submit_allocation", operation_key=operation_key, committed=True, record_key=allocation)
		return row

	# alias matching the task brief's alternate name for write B
	submit_payment = submit_allocation

	# -- write B (NON-idempotent variant, deliberately unsafe) ------------------

	def submit_allocation_unsafe(self, *, payment: str, invoice: str, amount: float) -> Allocation:
		"""Deliberately non-idempotent sibling of ``submit_allocation``: no idempotency key,
		no existing-check. Every call creates a brand-new submitted ``Allocation`` and
		decrements ``invoice`` again, so calling this twice for "the same" logical payment
		produces two committed rows and double-decrements the invoice -- proving blind
		replay is not a safe recovery strategy for this write shape.
		"""
		if not self.authorizer("submit_allocation_unsafe", {"payment": payment, "invoice": invoice, "amount": amount}):
			self._record(action="submit_allocation_unsafe", operation_key="<none>", committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"submit_allocation_unsafe denied for {payment}->{invoice}")

		name = f"ALLOC-UNSAFE-{next(self._allocation_counter):04d}"
		row = Allocation(name=name, payment=payment, invoice=invoice, amount=amount, operation_key="<none>", status="submitted")
		self.allocations[name] = row

		invoice_row = self.invoices.get(invoice)
		if invoice_row is not None:
			invoice_row.outstanding_amount -= amount

		self._record(action="submit_allocation_unsafe", operation_key="<none>", committed=True, record_key=name)
		return row

	# -- pending / non-critical -----------------------------------------------

	def update_followup_status(self, *, payment: str, status: str) -> None:
		"""Non-critical side channel, same treatment as W1's ``notify``: never appended to
		``commit_log``, task completion never depends on this landing.
		"""
		self.pending_followup_updates.append({"payment": payment, "status": status})


# ---------------------------------------------------------------------------
# W3 -- realistic order-onboarding flow (Issue 5: 5-8 step workload)
# ---------------------------------------------------------------------------
#
# W1/W2 are deliberately small (2 writes each) to keep the in-memory fault-injection matrix
# tractable. W3 is sized 5-8 steps, mixing reads, pure logic, and writes, to look like a
# plausible end-to-end "onboard a new order" Procedure -- the kind of task where a full
# agent replaying it from scratch would need meaningfully more tool calls/tokens than
# replaying a compiled Procedure. Steps (see ``run_in_memory`` below for the exact sequence
# this module runs):
#
#   1. read_account            (read)
#   2. read_prior_orders       (read)
#   3. check_eligibility       (pure logic, no I/O)
#   4. create_draft_order      (write A)
#   5. compute_pricing         (pure logic, no I/O)
#   6. submit_order            (write B)
#   7. update_fulfillment_status (pending / non-critical, mirrors W1/W2's "pending" step)
#   8. notify                  (pending / non-critical)
#
# This in-memory version mirrors W1/W2's style (dataclasses + ``_CommitLogMixin`` +
# ``Authorizer`` hook) so it is importable and testable under plain pytest with no bench.
# The REAL-bench counterpart (real HUF/Frappe DocType operations) is documented and driven
# separately from ``benchmarks/safe-deopt/results/w3_bench_report.md`` -- see that file for
# what actually ran against ``safe-deopt-verify.local``; this module intentionally does not
# import frappe anywhere, matching W1/W2's own "frappe-free" design requirement.


class EligibilityDenied(RuntimeError):
	"""Raised by ``check_eligibility`` when an account fails the eligibility check (pure
	logic -- no store mutation, no I/O; this exists to prove step 3 can short-circuit the
	whole flow before any write is attempted).
	"""


@dataclass
class Account:
	account_id: str
	name: str
	credit_hold: bool = False
	loyalty_tier: str = "standard"  # "standard" | "silver" | "gold"


@dataclass
class PriorOrder:
	order_id: str
	account_id: str
	amount: float
	status: str = "fulfilled"  # "fulfilled" | "cancelled" | "disputed"


@dataclass
class DraftOrder:
	name: str
	account_id: str
	items_subtotal: float
	operation_key: str
	discount_percent: float = 0.0
	total: float = 0.0
	status: str = "draft"  # "draft" | "submitted"
	fulfillment_status: str = "pending"  # "pending" | "in_progress" | "shipped"


def check_eligibility(account: Account, prior_orders: list[PriorOrder]) -> dict:
	"""Pure logic, no I/O (step 3): an account on credit hold, or with more disputed prior
	orders than fulfilled ones, is not eligible for a new order. Returns
	``{"eligible": bool, "reason": str | None}``; never mutates anything.
	"""
	if account.credit_hold:
		return {"eligible": False, "reason": "account_on_credit_hold"}

	disputed = sum(1 for o in prior_orders if o.status == "disputed")
	fulfilled = sum(1 for o in prior_orders if o.status == "fulfilled")
	if disputed > fulfilled:
		return {"eligible": False, "reason": "too_many_disputed_prior_orders"}

	return {"eligible": True, "reason": None}


def compute_pricing(account: Account, items_subtotal: float) -> dict:
	"""Pure logic, no I/O (step 5): a loyalty-tier discount applied to the draft order's
	subtotal. Returns ``{"discount_percent": float, "total": float}``; never mutates
	anything (the caller is responsible for writing the result onto the draft order).
	"""
	tier_discount = {"standard": 0.0, "silver": 0.05, "gold": 0.10}.get(account.loyalty_tier, 0.0)
	total = round(items_subtotal * (1 - tier_discount), 2)
	return {"discount_percent": tier_discount * 100, "total": total}


class OrderProcessingStore(_CommitLogMixin):
	"""In-memory stand-in for a real HUF/Frappe "new order onboarding" world.

	Reads
	-----
	``read_account`` / ``read_prior_orders`` never write and are never logged.

	Pure logic
	----------
	``check_eligibility`` / ``compute_pricing`` (module-level functions above) never touch
	the store at all -- they are pure functions over the data the reads already returned.

	Writes
	------
	- ``create_draft_order`` (write A): creates a draft order. Idempotent by an explicit
	  ``operation_key`` (same convention as W1/W2): a duplicate call returns the existing
	  draft rather than creating a second one.
	- ``submit_order`` (write B): submits a draft order (``draft`` -> ``submitted``).
	  Idempotent by ``operation_key``, distinct namespace from write A's keys, same as
	  W2's ``submit_allocation``: a duplicate call is a logged no-op, never double-submits.

	Pending / non-critical
	-----------------------
	- ``update_fulfillment_status`` and ``notify`` are both side channels: logged in
	  ``self.pending_fulfillment_updates`` / ``self.pending_notifications`` respectively,
	  never in ``commit_log``, and a task is allowed to be graded "complete" whether or not
	  either of them ever fires -- exactly W1/W2's treatment of their own pending steps.
	"""

	def __init__(self, *, authorizer: Authorizer = allow_all):
		self._init_log()
		self.authorizer = authorizer
		self.accounts: dict[str, Account] = {}
		self.prior_orders: dict[str, list[PriorOrder]] = {}
		self.draft_orders: dict[str, DraftOrder] = {}
		self._drafts_by_operation_key: dict[str, str] = {}
		self._submitted_operation_keys: set[str] = set()
		self._order_counter = itertools.count(1)
		self.pending_fulfillment_updates: list[dict] = []
		self.pending_notifications: list[dict] = []

	# -- seeding -----------------------------------------------------------

	def seed_account(self, account: Account) -> None:
		self.accounts[account.account_id] = account

	def seed_prior_order(self, order: PriorOrder) -> None:
		self.prior_orders.setdefault(order.account_id, []).append(order)

	# -- reads ---------------------------------------------------------------

	def read_account(self, account_id: str) -> Account | None:
		return self.accounts.get(account_id)

	def read_prior_orders(self, account_id: str) -> list[PriorOrder]:
		return list(self.prior_orders.get(account_id, []))

	# -- write A ---------------------------------------------------------------

	def create_draft_order(self, *, account_id: str, items_subtotal: float, operation_key: str) -> DraftOrder:
		"""Idempotent by ``operation_key``: a duplicate call returns the same draft."""
		existing_name = self._drafts_by_operation_key.get(operation_key)
		if existing_name is not None:
			self._record(
				action="create_draft_order", operation_key=operation_key, committed=False, record_key=existing_name, reason="duplicate_operation_key"
			)
			return self.draft_orders[existing_name]

		if not self.authorizer("create_draft_order", {"account_id": account_id, "items_subtotal": items_subtotal}):
			self._record(action="create_draft_order", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"create_draft_order denied for {account_id}")

		name = f"ORDER-{next(self._order_counter):04d}"
		draft = DraftOrder(name=name, account_id=account_id, items_subtotal=items_subtotal, operation_key=operation_key)
		self.draft_orders[name] = draft
		self._drafts_by_operation_key[operation_key] = name
		self._record(action="create_draft_order", operation_key=operation_key, committed=True, record_key=name)
		return draft

	# -- pure logic result applied onto the draft (not a commit-logged write itself) --------

	def apply_pricing(self, *, order: str, discount_percent: float, total: float) -> DraftOrder:
		"""Writes the result of ``compute_pricing`` onto the draft order. Deliberately NOT
		commit-logged: this mirrors "annotate a not-yet-submitted record with a computed
		field" -- a mutation, but not one whose ground truth a fault-injection wrapper needs
		to reason about, since it is always re-derivable from ``compute_pricing`` and never
		idempotency-sensitive (recomputing and re-applying the same inputs is always safe).
		"""
		draft = self.draft_orders[order]
		draft.discount_percent = discount_percent
		draft.total = total
		return draft

	# -- write B ---------------------------------------------------------------

	def submit_order(self, *, order: str, operation_key: str) -> DraftOrder:
		"""Idempotent submit: a duplicate call with the same ``operation_key`` (distinct
		namespace from write A's keys) is a logged no-op; submitting an already-submitted
		order via a different-but-equivalent key is also a no-op, never double-submits.
		"""
		draft = self.draft_orders.get(order)
		if draft is None:
			self._record(action="submit_order", operation_key=operation_key, committed=False, record_key=None, reason="not_found")
			raise KeyError(f"no such draft order {order}")

		if operation_key in self._submitted_operation_keys:
			self._record(action="submit_order", operation_key=operation_key, committed=False, record_key=order, reason="duplicate_operation_key")
			return draft

		if draft.status == "submitted":
			self._record(action="submit_order", operation_key=operation_key, committed=False, record_key=order, reason="already_submitted")
			return draft

		if not self.authorizer("submit_order", {"order": order}):
			self._record(action="submit_order", operation_key=operation_key, committed=False, record_key=None, reason="permission_denied")
			raise PermissionDenied(f"submit_order denied for {order}")

		draft.status = "submitted"
		self._submitted_operation_keys.add(operation_key)
		self._record(action="submit_order", operation_key=operation_key, committed=True, record_key=order)
		return draft

	# -- pending / non-critical -----------------------------------------------

	def update_fulfillment_status(self, *, order: str, status: str) -> None:
		"""Non-critical side channel, same treatment as W1's ``notify`` / W2's
		``update_followup_status``: never appended to ``commit_log``, task completion never
		depends on this landing. Still updates the in-memory record's field directly (a real
		bench version would be a plain ``.save()`` field update) so a test can observe it
		happened, but no ground-truth commit-log entry backs it.
		"""
		draft = self.draft_orders.get(order)
		if draft is not None:
			draft.fulfillment_status = status
		self.pending_fulfillment_updates.append({"order": order, "status": status})

	def notify(self, *, channel: str, message: str) -> None:
		"""Non-critical side channel. Never appended to ``commit_log``."""
		self.pending_notifications.append({"channel": channel, "message": message})
