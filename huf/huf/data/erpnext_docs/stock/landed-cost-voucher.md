---
title: "Landed Cost Voucher"
source_url: "https://docs.frappe.io/erpnext/landed-cost-voucher"
section: stock
---

# Landed Cost Voucher

## Overview

In ERPNext, you create a landed cost voucher against either a **Purchase Receipt** or **Purchase Invoice** to account for additional expenses incurred before inventory receipt.

## Key Prerequisites

### For Purchase Invoice
The "Update Stock" option must be enabled. According to the documentation, "If this field is unchecked, the Purchase Invoices will not be fetched in the Landed Cost Voucher."

### For Purchase Receipt
Selected items require the "Maintain Stock" setting to be active. The system notes that "If this field is not checked, the Items will not be displayed when you click **Get items from Purchase Receipt.**"

## Adding Additional Costs

When creating a landed cost voucher, you can include supplementary charges for items before they enter inventory. These charges automatically integrate into the **Item Valuation rate** and adjust the item rate accordingly. You can review the accounting impact through the accounting ledger accessible via **Purchase Receipt → View → Accounting Ledger**.

## Payment Options

Two approaches exist for settling additional charges:

1. **Direct Payment Method**: Generate a Payment Entry for the extra expenses, then optionally create a Purchase Invoice with "Is Paid" checked (the invoice isn't required unless you need accounting visibility)

2. **Supplier Invoice Method**: Create a Purchase Invoice for the supplier bearing the additional expenses, enabling clear accounting documentation through the landed cost process, followed by a corresponding Payment Entry
