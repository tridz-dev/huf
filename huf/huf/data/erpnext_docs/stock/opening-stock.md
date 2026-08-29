---
title: "Opening Stock"
source_url: "https://docs.frappe.io/erpnext/opening-stock"
section: stock
---

# Opening Stock

**Opening Stock represents the inventory amount and value available to a company at the start of an accounting period.**

The prior period's closing inventory automatically transitions as the opening inventory for the subsequent period.

## 1. Prerequisites

- Establish [Warehouses](/erpnext/warehouse).
- Connect Warehouses to corresponding accounting ledgers.

## 2. Opening Stock for Non-serialised Items

Access the [Stock Reconciliation](/erpnext/stock-reconciliation) page to record opening inventory.

## 3. Opening Stock for Serialised and Batched Items

Prepare [Batch](/erpnext/batch) and [Serial No](/erpnext/serial-no) records in advance. To document opening stock for serialised and batched items:

1. Navigate to **Stock > Stock Transactions > Stock Entry > New**.
2. Choose 'Material Receipt' from 'Stock Entry Type'.
3. Set `Is Opening` to `Yes`.
4. Choose the Warehouse in 'Default Target Warehouse'.
5. Within the Items table, specify Item Code, Qty and Basic rate.
6. For batched items, assign Batch No.
7. For serialised items, assign Serial No.
8. Save and Submit.

### 5. Related Topics

1. [Accounting Of Inventory Stock](/erpnext/accounting-of-inventory-stock)
2. [Stock Entry](/erpnext/stock-entry)
3. [Stock Reconciliation](/erpnext/stock-reconciliation)
