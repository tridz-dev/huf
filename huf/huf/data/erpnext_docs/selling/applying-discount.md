---
title: "Apply Discounts to Sales Transactions | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/applying-discount"
section: selling
---

# Apply Discounts to Sales Transactions | ERPNext Documentation

ERPNext enables businesses to apply reductions to sales documents in multiple ways. The system supports both "item-level and transaction-level discounts" that can be applied manually or automatically through rules.

## Key Discount Methods

**Item-Level Discounts**: Applied to individual line items through percentage or fixed amount. These are "calculated against the Price List Rate" and useful when different products require different reductions.

**Transaction-Level Discounts**: The Additional Discount section lets users apply reductions either on the Net Total (which "changes item Net Rate and Net Amount") or on the Grand Total (applied after taxes).

**Automatic Discounts**: For recurring scenarios, ERPNext offers Pricing Rules, Promotional Schemes, and Coupon Codes that evaluate eligibility automatically.

## Important Considerations

Users should confirm that discount fields are editable and understand how their tax configuration interacts with the chosen method. The documentation warns that "Inclusive taxes, charge types, rounding, and accounting configuration can affect" the final breakdown.

For accounting purposes, organizations can enable separate discount account posting through Selling Settings if their policy requires it.

## Decision Framework

The documentation provides a comparison table recommending specific methods based on requirements—from simple one-time item reductions to complex quantity-based promotions or website coupon codes.
