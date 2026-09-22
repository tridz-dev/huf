# Benchmark 4: Reconciliation seed data (reconstructed / synthetic fixture)

> This document is a reconstructed, synthetic fixture written for `huf/ai/tests/
> test_procedure_runtime_benchmark4.py`. It is not a recovered original. The actual seed
> rows the test's fake tool layer returns are hard-coded in the test file itself
> (`_INVOICES` / `_PAYMENTS`); this document is the human-readable description of that same
> data, kept here for `classify_payment`'s reference per the test's module docstring.

## Scope

Company: **Huf Retail Pvt Ltd**. One customer/company (`CUST-0009` / `Globex Overseas`)
and its invoice/payment are deliberately out of scope, to prove the run's company filter
actually excludes them rather than merely ignoring the field.

## Open invoices (14 in scope + 1 out of scope)

| Invoice | Customer | Outstanding | Company |
|---|---|---|---|
| SINV-4001 | CUST-0001 | 5,000.00 | Huf Retail Pvt Ltd |
| SINV-4002 | CUST-0001 | 9,000.00 | Huf Retail Pvt Ltd |
| SINV-4010 | CUST-0002 | 12,000.00 | Huf Retail Pvt Ltd |
| SINV-4011 | CUST-0002 | 12,000.00 | Huf Retail Pvt Ltd |
| SINV-4020 | CUST-0004 | 7,000.00 | Huf Retail Pvt Ltd |
| SINV-4021 | CUST-0004 | 8,000.00 | Huf Retail Pvt Ltd |
| SINV-4022 | CUST-0004 | 15,000.00 | Huf Retail Pvt Ltd |
| SINV-4030 | CUST-0006 | 4,500.00 | Huf Retail Pvt Ltd |
| SINV-4031 | CUST-0006 | 6,200.00 | Huf Retail Pvt Ltd |
| SINV-4040 | CUST-0007 | 22,000.00 | Huf Retail Pvt Ltd |
| SINV-4050 | CUST-0008 | 3,000.00 | Huf Retail Pvt Ltd |
| SINV-4051 | CUST-0008 | 3,000.00 | Huf Retail Pvt Ltd |
| SINV-4052 | CUST-0008 | 3,000.00 | Huf Retail Pvt Ltd |
| SINV-4060 | CUST-0003 | 12,000.00 | Huf Retail Pvt Ltd |
| SINV-9010 | CUST-0009 | 5,000.00 | **Globex Overseas** (out of scope) |

In-scope total outstanding: **121,700.00**.

## Unallocated payments (8 in scope + 1 out of scope)

| Payment | Customer | Amount | Company |
|---|---|---|---|
| PE-4001 | CUST-0001 | 5,000.00 | Huf Retail Pvt Ltd |
| PE-4002 | CUST-0001 | 9,000.00 | Huf Retail Pvt Ltd |
| PE-4010 | CUST-0002 | 12,000.00 | Huf Retail Pvt Ltd |
| PE-4020 | CUST-0004 | 15,000.00 | Huf Retail Pvt Ltd |
| PE-4030 | CUST-0006 | 4,500.00 | Huf Retail Pvt Ltd |
| PE-4040 | CUST-0007 | 22,000.00 | Huf Retail Pvt Ltd |
| PE-4050 | CUST-0008 | 3,000.00 | Huf Retail Pvt Ltd |
| PE-4099 | CUST-0003 | 9,999.00 | Huf Retail Pvt Ltd |
| PE-9099 | CUST-0009 | 5,000.00 | **Globex Overseas** (out of scope) |

## Expected classification (`classify_payment`: single exact matches, then bounded
2-3 invoice combinations)

- **Resolved (4):** PE-4001 -> SINV-4001; PE-4002 -> SINV-4002; PE-4030 -> SINV-4030;
  PE-4040 -> SINV-4040 -- each payment matches exactly one invoice's outstanding amount
  and no combination also matches.
- **Ambiguous (3):**
  - PE-4010 (12,000.00) matches *both* SINV-4010 and SINV-4011 (12,000.00 each) as single
    candidates -- two equally valid single-invoice matches, genuinely ambiguous.
  - PE-4020 (15,000.00) matches SINV-4022 (15,000.00) as a single AND the 2-invoice
    combination SINV-4020+SINV-4021 (7,000.00 + 8,000.00 = 15,000.00) -- a single match
    competing with a combo match.
  - PE-4050 (3,000.00) matches all three of SINV-4050/4051/4052 (3,000.00 each) as
    separate single candidates.
- **Unmatched (1):** PE-4099 (9,999.00 for CUST-0003) has no invoice, and no 2- or
  3-invoice combination, that sums to 9,999.00 against CUST-0003's only open invoice
  (SINV-4060, 12,000.00).
- **Out of scope, never classified:** PE-9099 -- excluded by the company filter before
  the `foreach` over payments even begins.
