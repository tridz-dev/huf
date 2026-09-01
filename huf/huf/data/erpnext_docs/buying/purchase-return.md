---
title: "Purchase Return"
source_url: "https://docs.frappe.io/erpnext/purchase-return"
section: buying
---

# Purchase Return

**A purchased Item being returned is known as a Purchase Return.**

The Purchase Return feature enables returning products to suppliers for reasons such as defects, quality issues, or excess inventory.

## 1. Prerequisites
Before creating a Purchase Return, prepare these items first:

* [Item](/erpnext/item)
* [Purchase Invoice](/erpnext/purchase-invoice)

Or

* [Purchase Receipt](/erpnext/purchase-receipt)

## 2. How to create a Purchase Return

1. Open the original Purchase Receipt corresponding to the supplier's delivery.

2. Select 'Create > Return', which generates a new Purchase Receipt with 'Is Return' enabled. "Items, Rate, and taxes will [appear as] negative numbers."

3. Upon submitting the return, the system decreases item quantities in the specified Warehouse. Stock valuation adjusts upward based on the original purchase rate.

4. In the Accounting Ledger, the Stock In Hand account receives a credit while the Stock Received but Not Billed account receives a debit.

With Perpetual Inventory enabled, the system additionally posts accounting entries to warehouse accounts to align warehouse balances with Stock Ledger figures.

## 3. Impact on Stock Return via Purchase Receipt

When creating a Purchase Return against a Purchase Receipt:

* The **Returned Quantity** updates in both the original Purchase Receipt and any linked Purchase Order.

* The original Purchase Receipt's status becomes **Return Issued** if fully returned.

## 4. Related Topics

1. [Sales Return](/erpnext/sales-return)
2. [Perpetual Inventory](/erpnext/perpetual-inventory)
