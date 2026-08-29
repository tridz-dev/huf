---
title: "Price Lists"
source_url: "https://docs.frappe.io/erpnext/price-lists"
section: stock
---

# Price Lists

A Price List is a collection of Item Prices that can be designated for selling, buying, or both purposes. ERPNext enables organizations to maintain multiple selling and buying price lists simultaneously.

## Use Cases

Price Lists serve several business scenarios:

- Different pricing across geographical zones (accounting for shipping variations)
- Multiple currency support
- Region-based pricing strategies
- Customer-specific rate structures
- Currency-dependent pricing models

The system separates buying prices from selling prices, storing them independently to reflect different cost structures.

## Access Location

Navigate to: Home > Selling/Buying/Stock > Items and Pricing > Price List

## How to Use a Price List

Price Lists function in several key ways:

- They are referenced when creating item prices to document selling or buying rates
- Specific countries can be assigned within a Price List configuration
- Disabling occurs through unchecking the 'Enabled' checkbox, preventing selection in sales and purchase transactions
- **Price Not UOM Dependent**: This feature addresses scenarios where purchase and sales units differ. For example, an item purchased in boxes but sold in individual units. When unchecked, prices only apply to the recorded unit. When enabled, the system automatically calculates prices for different units based on conversion ratios.
- The system automatically generates Standard Buying and Selling Price Lists

## Key Features

Multiple Price Lists can be established and assigned to specific customers for automatic selection during transactions. Item prices then automatically update based on the associated Price List.

### Related Topics

- [Item Price](/erpnext/item-price)
