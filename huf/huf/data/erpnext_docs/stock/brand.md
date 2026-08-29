---
title: "Brand"
source_url: "https://docs.frappe.io/erpnext/brand"
section: stock
---

# Brand

A Brand serves to identify items under a specific name. Typically, this represents the manufacturer or packer of a product—for instance, Apple manufactures laptops under that brand name. However, the brand need not be the actual manufacturer; it's primarily the name consumers recognize the product by. An example would be a plastic cup manufacturer licensing their product to a larger company that sells them under their own brand identity.

Within ERPNext, brands can be attached to Items to facilitate identification and establish default settings.

To locate the Brand list, navigate to:

> Home > Selling > Sales > Brand

## 1. How to Create a Brand

1. Access the Brand list and select New.
2. Input the Brand name and optionally add a description.
3. Save the entry.

Once created, this Brand can be linked with various Items.

## 2. Features

### 2.1 Setting defaults for Items of this Brand

Several defaults can be configured for a Brand. When assigning this brand to an Item, these defaults populate automatically during Sales and Purchase transactions involving that Item.

- **Default Warehouse**: The storage or sourcing location for the Item based on transaction type.
- **Default Price List**: The Price List retrieved during Purchase and Sales transactions.

#### Purchase Defaults

For Purchase transactions (Purchase Order, Purchase Receipt, Purchase Invoice), these defaults apply:

- Default Buying Cost Center
- Default Supplier
- Default Expense Account

#### Sales Defaults

For Sales transactions (Sales Order, Delivery Note, Sales Invoice), these defaults apply:

- Default Selling Cost Center
- Default Income Account

## 3. Related Topics

1. [Purchase Order](/erpnext/purchase-order)
2. [Sales Order](/erpnext/sales-order)
3. [Purchase Receipt](/erpnext/purchase-receipt)
4. [Delivery Note](/erpnext/delivery-note)
5. [Sales Invoice](/erpnext/sales-invoice)
6. [Purchase Invoice](/erpnext/purchase-invoice)
