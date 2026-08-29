---
title: "Material Transfer from Delivery Note and Purchase Receipt"
source_url: "https://docs.frappe.io/erpnext/material-transfer-from-delivery-note"
section: stock
---

# Material Transfer from Delivery Note and Purchase Receipt

In ERPNext, material transfers can be created through [Stock Entry](/erpnext/stock-entry.html) documents, but certain business scenarios benefit from using Delivery Notes and Purchase Receipts instead.

## Material Transfer from Delivery Note

### Scenarios

1. Transferring materials from stores to a project site while presenting the transaction as a Delivery Note to the client.

2. Meeting statutory requirements where taxes must be applied to each material transfer—easier to manage in a Delivery Note than in Stock Entry.

### Steps

#### Enable Target Warehouse

The Delivery Note Item doctype includes a hidden Target Warehouse field (formerly Customer Warehouse). Enable it through [Stock Settings](/erpnext/stock-settings) by activating "Allow Material Transfer From Delivery Note and Sales Invoice".

The selected customer should represent the same company. Configure the customer record by enabling 'Is Internal Customer' and specifying your company in the 'Represents Company' field.

#### Select Warehouses

When creating a Delivery Note for material transfer:
- Select the source warehouse as "From Warehouse"
- In Customer Warehouse, specify where the material should transfer

Upon submission, stock decreases from "From Warehouse" and increases in "Customer Warehouse".

## Material Transfer from Purchase Receipt

### Scenarios

Statutory requirements often necessitate tax application on material transfers, which is more straightforward to manage through Purchase Receipt rather than Stock Entry.

### Steps

#### Enable Supplier Warehouse

Enable the Supplier Warehouse field in [Stock Settings](/erpnext/stock-settings).

Configure the supplier by enabling 'Is Internal Supplier' and selecting your company in 'Represents Company'.

#### Select Warehouses

When creating a Purchase Receipt for material transfer:
- Select the destination as "Accepted Warehouse"
- In Supplier Warehouse, specify the source warehouse

Upon submission, stock decreases from "Supplier Warehouse" and increases in "Accepted Warehouse".
