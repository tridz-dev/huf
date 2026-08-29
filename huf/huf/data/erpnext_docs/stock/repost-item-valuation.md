---
title: "Repost Item Valuation"
source_url: "https://docs.frappe.io/erpnext/repost-item-valuation"
section: stock
---

# Repost Item Valuation

## Overview

The **Repost Item Valuation** feature in ERPNext is used to recalculate item valuation, stock balances, and related accounting values when inconsistencies occur due to backdated entries or stock ledgers related issues.

This process ensures that inventory valuation and General Ledger (GL) entries remain accurate and consistent.

---

## When to Use Repost Item Valuation

Use this feature in the following scenarios:

* Backdated stock transactions are created or modified
* Stock Ledger Entries (SLEs) have incorrect balances
* Negative stock issues appear due to reposting problems
* After fixing bugs or applying patches related to stock or valuation
* Data migration or bulk import of stock transactions

---

## What Repost Item Valuation Does

Reposting item valuation performs the following actions:

* Recalculates **Stock Ledger Entries (SLEs)** from a specific point in time
* Recomputes **Running Available Stock** and **Stock Balance**
* Re-evaluates item valuation based on the valuation method
* Updates **Stock Value** and **Valuation Rate**
* Reposts related **General Ledger entries**, if required

---

## Types of Reposting

### 1. Automatic Reposting

ERPNext automatically creates reposting entries when:

* Backdated stock transactions are saved
* System detects that reposting is required

These entries are processed in the background by scheduled jobs.

---

### 2. Manual Repost Item Valuation

Users can manually trigger reposting using the **Repost Item Valuation** tool.

#### Steps:

1. Search **Repost Item Valuation**.
2. Click on **New**.
3. Fill in the required details:

   * **Company** – Company for which reposting is required
   * **Item Code** (optional) – Repost valuation for a specific item
   * **Warehouse** (optional) – Limit reposting to a warehouse
   * **Posting Date** and **Posting Time** – Starting point for reposting
4. Save the document.
5. Click on **Start Reposting**.

The system will enqueue reposting jobs based on the provided filters.

---

## Using Stock Ledger Variance Report with Reposting

Before triggering reposting, it is recommended to use the **Stock Ledger Variance** report to:

* Identify incorrect Stock Ledger Entries
* Filter rows with quantity or balance differences
* Select affected entries and create reposting entries directly

This helps reduce the scope of reposting and improves performance.

---

## Performance Considerations

* Reposting can be resource-intensive for large datasets
* It is recommended to:

  * Limit reposting by item, warehouse, or date
  * Run reposting during non-peak hours
* Avoid triggering full reposting unless necessary

---

## Common Issues and Troubleshooting

### Reposting Takes Too Long

* Check the number of affected entries
* Narrow down filters (Item, Warehouse, Date)
* Ensure background workers are running

### Negative Stock Errors After Reposting

* Verify inward entries exist before outward transactions
* Check posting dates and times
* Use Stock Reconciliation if required

### GL Entries Not Updated

* Ensure **Update Stock** is enabled for relevant transactions
* Confirm that accounting reposting is allowed

---

## Best Practices

* Always review stock data using reports before reposting
* Avoid frequent backdated transactions
* Keep ERPNext updated to the latest patch version
* Use reposting tools incrementally instead of full reprocessing

---

## Notes

* Repost Item Valuation affects historical data; use it carefully
* Reposting will change the closing balances of the respective financial year, so use it carefully.
* Avoid using reposting for closed financial years, as it will change the closing balances of the closed financial years.
* Users should have appropriate permissions to perform reposting
* Applicable primarily to stock-impacting transactions

---

The **Repost Item Valuation** feature is a critical maintenance tool that helps ensure inventory accuracy and accounting integrity in ERPNext.
