---
title: "Add Margin to Quotations and Sales Orders | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/adding-margin"
section: selling
---

# Add Margin to Quotations and Sales Orders | ERPNext Documentation

## Overview

"Margin increases an item's transaction Rate above its Price List Rate." ERPNext supports both percentage-based and fixed-amount margins, which can be applied manually to individual items or automatically through Pricing Rules.

## Manual Margin Application

To add margin directly to a quotation or sales order:

1. Create a Quotation or Sales Order
2. Select the Customer, Price List, and Item
3. Open the item-row editor using the pencil icon
4. Set **Margin Type** to either **Percentage** or **Amount**
5. Enter the **Margin Rate or Amount**
6. Review the calculated Rate and Amount
7. Save the document

## Margin Calculation Formulas

**Fixed margin:** `Rate = Price List Rate + Margin Amount`

**Percentage margin:** `Rate = Price List Rate + (Price List Rate × Margin Percentage ÷ 100)`

Example calculation:
- Price List Rate: $1,000
- Margin: 15%
- Resulting Rate: $1,150

## Automated Margins via Pricing Rules

Configure a Pricing Rule to apply consistent margins across repeatable scenarios:

1. Create or open a Pricing Rule
2. Set applicability conditions (Item, Customer, quantity, validity, etc.)
3. Configure margin settings in the Margin section
4. Save and enable the rule
5. Test on new transactions

## Key Distinctions

"Margin adds a markup to the Price List Rate" while "discounts reduce a price or total." These serve different purposes and should not be combined without clear documentation.

## Prerequisites

Before applying margins, ensure:
- Required Item exists
- Selling Price List is created
- Item Price record supplies the Price List Rate

## Related Resources

- [Price Lists](/erpnext/price-lists)
- [Item Price](/erpnext/item-price)
- [Pricing Rule](/erpnext/pricing-rule)
- [Applying a Discount](/erpnext/applying-discount)
- [Selling Settings](/erpnext/selling-settings)
