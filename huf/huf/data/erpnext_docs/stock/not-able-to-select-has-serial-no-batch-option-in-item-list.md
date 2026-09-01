---
title: "Cannot enable Serial and Batch Number"
source_url: "https://docs.frappe.io/erpnext/not-able-to-select-has-serial-no-batch-option-in-item-list"
section: stock
---

# Cannot enable Serial and Batch Number

The system prevents activating serial and batch tracking options after inventory transactions have occurred. This is an intentional design choice to maintain data integrity.

## Solution Overview

If you need to enable these features, you have two primary approaches:

**Option 1: Clear Existing Stock**
- Remove all current stock transactions for the item
- This allows you to reactivate the serial/batch options

**Option 2: Create a Duplicate Item**
- Maintain the original item without serial/batch tracking
- Establish a new item with these features enabled
- Transfer stock to the new item

## Step-by-Step Process

1. **Zero out current inventory** using either the Stock Reconciliation Tool or a Material Issue stock entry to reduce stock to zero.

2. **Inward serialized inventory** via material receipt with the serial/batch options enabled. Review the "[Opening Stock Balance Entry for Serialized and Batch Item](/erpnext/opening-stock-balance-entry-for-serialized-and-batch-item)" documentation for detailed guidance.

3. **Disable the original item** to prevent its selection in future transactions.

## Important Note

"If you want to maintain the same item code, you will need to rename the existing items, and then create the new item as per the actual item code." Otherwise, the item will operate under a different code designation.
