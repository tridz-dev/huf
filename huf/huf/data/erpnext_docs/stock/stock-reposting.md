---
title: "Stock Ledger Variance Report"
source_url: "https://docs.frappe.io/erpnext/stock-reposting"
section: stock
---

# Stock Ledger Variance Report

The Stock Ledger Variance report in ERPNext is designed to help users identify and correct problematic Stock Ledger Entries where "the Running Available Stock and Stock Balance are inconsistent."

## Key Capabilities

This report enables users to:

* Identify Stock Ledger Entries with incorrect running balances
* Detect stock quantity mismatches between calculated and stored values
* Repost affected entries to fix stock inconsistencies

## Report Filters

Users can apply specific filters to locate problematic entries:

* **Quantity (A - B)**: Finds ledgers with incorrect balance quantities
* **Value (G - D)**: Finds ledgers with incorrect balance values
* **Valuation (I - K)**: Finds ledgers with incorrect valuation rates

## Correction Process

To address detected inconsistencies:

1. Select the rows showing problems
2. Click on Create Reposting Entries
3. The system generates reposting entries for selected records
4. Re-run the report after completion to confirm resolution

## Important Considerations

* Reposting duration varies based on the number of affected entries
* Schedule reposting during off-peak hours for optimal performance
* Always verify stock balances once reposting concludes

## When to Use

This report proves valuable in these scenarios:

* Following resolution of reposting-related issues
* When unexpected negative stock errors surface
* After importing or creating backdated stock transactions
* During stock audits or reconciliations
