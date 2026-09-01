---
title: "Control Item Rate Changes Through the Sales Cycle"
source_url: "https://docs.frappe.io/erpnext/change-the-rate-of-items-in-the-sales-cycle"
section: selling
---

ERPNext enables validation of item rates as they progress through the sales workflow. This feature helps ensure that confirmed order prices remain stable from Sales Orders through Delivery Notes and Sales Invoices.

## Initial Setup Requirements

Before implementing rate controls, verify:

- Item pricing structures and designated Price Lists are configured
- Team members with approval authority are identified
- Whether your workflow needs warnings or enforcement
- How to handle legitimate amendments and customer returns

Note: This setting complements but does not replace comprehensive pricing policies. Document exceptions and approval authority.

## Enabling Rate Validation

Navigate to Selling Settings and locate the Item Price Settings area:

1. Activate **Maintain Same Rate Throughout Sales Cycle**
2. Select **Action If Same Rate Is Not Maintained**:
   - **Warn**: Users receive notification but can proceed
   - **Stop**: System prevents inconsistent rates
3. If Stop is selected, designate an override role (when available)
4. Confirm changes

[View configuration screenshot](https://novacompanies.m.frappe.cloud/files/sales-cycle-rate-settings.png)

## Validation Testing Process

1. Create and submit a Sales Order with an item price
2. Generate a Delivery Note or Sales Invoice from that order
3. Click the pencil icon to access the complete item details
4. Modify the Rate value
5. Attempt to save and verify ERPNext responds per your settings

[View item rate change example](https://novacompanies.m.frappe.cloud/files/sales-cycle-rate-change.png)

Stock status indicators appear before each Item Code—green signals availability, red indicates shortage.

## Authorized Rate Adjustments

When commercial terms legitimately change, follow these documented approaches:

- Amend the Sales Order if terms shifted before delivery
- Use [Update Items](/erpnext/amending-sales-order-after-submit) for supported post-submission workflows
- Process Credit Notes or returns for invoice corrections
- Apply authorized overrides only when policy explicitly permits

Avoid undocumented downstream rate modifications to reconcile totals.

## Pricing Factors and Interactions

Item rates can be affected by multiple sources:

- Item Price and Price List configuration
- [Pricing Rules](/erpnext/pricing-rule) applied
- [Promotional Schemes](/erpnext/promotional-scheme)
- Margin or discount at item level
- Additional Discount percentage
- Exchange rates for multi-currency transactions
- Manual Rate entry (when permitted by access controls)

Same-rate validation examines the mapped sales-cycle rate. It does not restrict all upstream pricing configurations.

## Key Configuration Options

| Setting | Function |
|---------|----------|
| Maintain Same Rate Throughout Sales Cycle | Activates rate comparison against upstream source |
| Action: Warn | Displays alert; allows document completion |
| Action: Stop | Prevents rate inconsistency |
| Override Role | Permits authorized users to bypass Stop blocks |
| Allow User to Edit Price List Rate | Governs Price List Rate field editability only |

## Resolution Guide

| Issue | Investigation Steps |
|-------|---------------------|
| No validation message | Verify downstream document originates from Sales Order; confirm setting is saved |
| Override unavailable | Check role configuration matches user's assigned roles |
| Rate changes before linking | Examine Item Prices, Pricing Rules, discounts, currency conversion, source document |
| Return/credit blocked | Apply appropriate return or amendment process |
| Rate vs. Price List Rate confusion | Clarify reference rate, margin, discount, and final transaction rate relationships |

## Common Questions

**Does this apply to independent invoices?**

The feature targets linked sales cycles. Standalone invoices lack a Sales Order rate for comparison.

**When should Warn versus Stop be selected?**

Choose Warn for workflows where exceptions receive later review. Select Stop when approval must occur before saving.

**Can authorized personnel override Stop?**

Yes, provided your ERPNext version includes and has configured the override-role field.

**Does this prevent Pricing Rules from applying?**

No. Pricing Rules continue functioning as part of rate calculation. Validate the combined behavior.

## Additional Resources

- [Selling Settings](/erpnext/selling-settings)
- [Sales Order](/erpnext/sales-order)
- [Amending Sales Order after Submit](/erpnext/amending-sales-order-after-submit)
- [Pricing Rule](/erpnext/pricing-rule)
- [Applying a Discount](/erpnext/applying-discount)
