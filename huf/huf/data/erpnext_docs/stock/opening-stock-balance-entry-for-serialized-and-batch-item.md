---
title: "Opening Stock Balance Entry for Serialized and Batch Item"
source_url: "https://docs.frappe.io/erpnext/opening-stock-balance-entry-for-serialized-and-batch-item"
section: stock
---

# Opening Stock Balance Entry for Serialized and Batch Item

Items requiring Serial No. and Batch No. tracking need opening stock balance entries created through Stock Entry rather than Stock Reconciliation.

## Why Not Use Stock Reconciliation?

Stock levels for serialized items depend on Serial No. counts. Since Stock Reconciliation only updates quantities—not Serial Nos. or Batch Nos.—it cannot properly establish opening balances for these item types.

## Steps to Create Opening Balance Entry

**Step 1: Access Stock Entry**
Navigate to `Stock > Stock Entry > New`

**Step 2: Set Purpose**
Choose `Material Receipt` as the Stock Entry Purpose.

**Step 3: Set Posting Date**
Enter the date when opening balance should be recorded.

**Step 4: Select Target Warehouse**
Specify the warehouse receiving the opening stock.

**Step 5: Choose Items**
Select items requiring opening balance updates.

**Step 6: Input Quantities and Identifiers**
- For serialized items: Enter quantity matching the number of Serial Nos.
- Provide individual Serial Nos. or rely on automatic generation if configured with a prefix
- For batch items: Assign a Batch ID and ensure the batch master exists

**Step 7: Set Valuation Rate**
Enter per-unit valuation rates. Different rates require separate rows.

**Step 8: Configure Difference Account**
The perpetual inventory system requires balancing entries. Use a Temporary Opening account as the Difference Account to balance debit/credit entries.

**Step 9: Submit**
Save and submit the Stock Entry to post ledger transactions and finalize opening balances.
