---
title: "Calculating Freight in taxes in ERPNext"
source_url: "https://docs.frappe.io/erpnext/calculatin-freight-in-taxes-in-erpnext"
section: buying
---

# Calculating Freight in taxes in ERPNext

## Use case: To calculate freight forwarding charges with tax rate

When freight needs to be incorporated into forwarding charges as a tax rate, follow these steps:

* Create a ledger account in the Chart of Accounts specifically for taxes, or utilize an existing GST tax account within your taxation setup for freight charge calculations.

* Establish an Item named **Freight and Forwarding**

* Generate a Purchase Invoice for your Supplier and include this item to determine freight-related taxes. You can base the freight tax calculation on either the Net total or Item Quantity, depending on your company's policy.
