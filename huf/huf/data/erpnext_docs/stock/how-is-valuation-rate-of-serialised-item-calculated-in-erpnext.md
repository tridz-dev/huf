---
title: "Serialised Item Valuation Rate Calculation"
source_url: "https://docs.frappe.io/erpnext/how-is-valuation-rate-of-serialised-item-calculated-in-erpnext"
section: stock
---

# Serialised Item Valuation Rate Calculation

## Overview

In ERPNext, an item's stock **valuation rate** is refreshed when these transactions occur:

1. Purchase Receipt
2. Stock Entry of type Material Receipt
3. Stock Reconciliation for updating stock opening balance

## Valuation Methods

ERPNext offers two valuation approaches: FIFO and Moving Average. Organizations can designate their preferred method either per individual item or globally through Stock Settings.

## Special Handling for Serialised Items

An important distinction exists for serialised products. While standard items follow the valuation method configured in their settings, serialised items operate differently. As stated in the documentation, "these settings are *ignored*" for serialised items.

Instead of referencing the Item Master's valuation method, serialised items derive their valuation rate from "the *first incoming stock entry rate*." Subsequently, this rate updates based on additional transactions involving that particular item.

### Example

The documentation illustrates this with a "Macbook Pro" serialised item. Rather than applying the configured valuation method, the system captures the initial purchase rate of ₹199.80 from the first stock entry and adjusts it according to subsequent transactions.

## Additional Resources

For comprehensive information about ERPNext's inventory management capabilities, consult the [Stock module documentation](https://erpnext.com/docs/user/manual/en/stock).
