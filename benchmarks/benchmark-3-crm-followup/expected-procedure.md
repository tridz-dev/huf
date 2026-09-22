# Benchmark 3: CRM Follow-up (reconstructed / synthetic fixture)

> This document is a reconstructed, synthetic fixture written for `huf/ai/tests/
> test_benchmark3_write_runtime.py`. It is not a recovered original; the original brief
> this benchmark refers to is not available on this machine. It exists to give the write
> node's docstrings (see `huf/ai/graph/idempotency.py`) and the test file's own graph a
> human-readable description of the procedure they encode in JSON.

## Goal

For a set of selected customers, find their overdue Sales Invoices and make sure a
collections follow-up `ToDo` exists for each one -- without ever creating a duplicate
`ToDo` for the same (invoice, collector) pair, and without losing track of partial
progress if a write fails partway through a run.

## Pseudocode

```
read customer                      # fetch_overdue_invoices_for(selected_customers, company)
for each (customer, invoice) in the fetched rows:
    read open items / qualify      # deterministic_qualification_check(invoice)
    if not qualifies:
        mark(row, outcome=skipped_not_qualified)
        continue

    read existing follow-up        # existing_followup_check(invoice, allocated_to)
    if a follow-up ToDo already exists:
        write A: (skipped -- already_existed=True, created=False)
    else:
        write A: create_todo(invoice, allocated_to)   # create followup ToDo
        # idempotency_key derived from (procedure_name, procedure_version,
        # normalised_inputs, target_identity) -- content-derived, NOT run-scoped, so a
        # second attempt at the identical logical write (same invoice, same collector,
        # same procedure version) is recognised as the same operation even across runs.

    verify                          # ToDo was either created just now or already existed
    write B: update linked record   # mark_row(customer, invoice, qualifies, created, already_existed)
                                     # -- the per-row audit trail folded into the run's summary

pending notify                      # compute_summary aggregates all rows into one honest
                                     # top-level status: success / partial_success / failure
```

## Recovery semantics

- A write node (`create_todo`) MUST declare a `recovery` mode (`retry`, `resume`, `abort`,
  or `compensate`) and carry an `idempotency_key`. A node missing either fails the whole
  run closed rather than guessing a default -- this is the runtime's own contract, not a
  business rule of this specific procedure.
- `resume` semantics: if a run fails partway through (e.g. a transient `frappe.db`
  deadlock on one invoice), a later replay of the exact same input must converge to
  exactly one `ToDo` per (invoice, collector) pair -- the rows that already succeeded are
  recognised via `existing_followup_check` (a read-before-write guard) and are not
  recreated; only the row that previously failed proceeds to a real write.
- `retry` semantics: a single transient fault on `create_todo` is retried exactly once,
  inline, within the same run -- no second `execute_procedure` call needed.

## Seed shape used by the test's fake tool layer

- `CUST-0001` / `SINV-2001` -- no prior ToDo, qualifies, gets created.
- `CUST-0002` / `SINV-2002` -- a `ToDo` (`TODO-3001`) already exists for the configured
  collector, so `create_todo` is a no-op (`already_existed`).
- `CUST-0004` / `SINV-2004` -- no prior ToDo, qualifies, gets created.
- `CUST-0006` / `SINV-2006A`, `SINV-2006B` -- both qualify; the fault-injection test makes
  `SINV-2006B`'s first `create_todo` call fail transiently (does not repeat on replay).
