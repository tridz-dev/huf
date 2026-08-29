---
title: "Track Purchases In Accounts"
source_url: "https://docs.frappe.io/erpnext/track-purchases-in-accounts"
section: stock
---

# Track Purchases In Accounts

:::note
ERPNext version 16 feature
:::

## Overview

According to industry standards, the Cost of Goods Sold is calculated as:

:::note
COGS = Opening + Purchases - Closing
:::

While the opening and closing figures are easily available from the Stock Balance report, determining the purchases component is challenging — the "Stock Received but Not Billed" account may not function properly when using Purchase Invoices with the 'Update Stock' option enabled.

Also, purchases are not the only way stock value changes. Stock Entry, Stock Reconciliation and Landed Cost Voucher also add or remove stock value, and these movements were not visible anywhere in the Profit & Loss or Trial Balance reports.

## Solution

ERPNext addresses this through two pairs of accounts:

- **Purchase Expense Account** and **Purchase Expense Contra Account** — booked when stock is received through a Purchase Receipt or a Purchase Invoice (with 'Update Stock' enabled)
- **Expenses Added To Stock Account** and **Expenses Added To Stock Contra Account** — booked when stock value changes through a Stock Entry, Stock Reconciliation or Landed Cost Voucher

When these vouchers are recorded, "the accounts receive equal debits and credits, resulting in zero net impact on the books." However, this allows the purchase amounts and the value added to (or removed from) stock to appear in the Profit & Loss and Trial Balance reports, making the COGS components directly visible.

## Enabling the Feature

Go to **Accounts Settings > Stock Expense Accounting** and enable the **Book Stock Expense GL Entries** checkbox.

- When disabled (default), no Purchase Expense or Expenses Added To Stock entries are booked.
- When enabled, the accounts become mandatory depending on the voucher type:

| Voucher Type | Mandatory Accounts |
|---|---|
| Purchase Receipt / Purchase Invoice (Update Stock) | Purchase Expense Account and Purchase Expense Contra Account |
| Stock Entry / Stock Reconciliation / Landed Cost Voucher | Expenses Added To Stock Account and Expenses Added To Stock Contra Account |

A company that has not configured a pair of accounts at all is simply skipped — no entries are booked for it. If only one account of a pair is set, the system stops the voucher with a message asking to set the missing account. This way, in a multi-company setup, each company opts in by configuring its accounts.

> **Note for upgrading sites:** if any Company or Item Default already uses a Purchase Expense Account, the checkbox is enabled automatically during migration so that existing purchase expense entries continue to be booked.

## Company Master Configuration

Users can set the default accounts in the Company master:

- **Purchase Expense** section: Purchase Expense Account and Purchase Expense Contra Account
- **Stock Expense** section: Expenses Added To Stock Account and Expenses Added To Stock Contra Account

The accounts can also be set per item or item group in the **Item Defaults** table. The system resolves the accounts in the following order:

1. Item Defaults (on the Item)
2. Item Group Defaults
3. Brand Defaults
4. Company

## Accounting Entries

For a Purchase Receipt of value 10,000 (existing behaviour):

| Account | Debit | Credit |
|---|---|---|
| Purchase Expense Account | 10,000 | |
| Purchase Expense Contra Account | | 10,000 |

For the stock vouchers, the Expenses Added To Stock pair mirrors the stock value movement:

| Transaction | Entry |
|---|---|
| Stock Entry — Material Receipt (10,000 in) | Dr Expenses Added To Stock 10,000 / Cr Expenses Added To Stock Contra 10,000 |
| Stock Entry — Material Issue (5,000 out) | Dr Expenses Added To Stock Contra 5,000 / Cr Expenses Added To Stock 5,000 |
| Stock Entry — Manufacture (10,000 finished goods in) | Dr Expenses Added To Stock 10,000 / Cr Expenses Added To Stock Contra 10,000 |
| Stock Reconciliation (Add 10,000) | Dr Expenses Added To Stock 10,000 / Cr Expenses Added To Stock Contra 10,000 |
| Stock Reconciliation (Less 5,000) | Dr Expenses Added To Stock Contra 5,000 / Cr Expenses Added To Stock 5,000 |
| Landed Cost Voucher (10,000 charges) | Dr Expenses Added To Stock 10,000 / Cr Expenses Added To Stock Contra 10,000 |

A plain Material Transfer between warehouses does not change the total stock value, so nothing is booked.

"Since every pair nets to zero, the Balance Sheet is unaffected — the accounts exist purely to make the stock value movements visible" in financial reports for cost analysis purposes.
