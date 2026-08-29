---
title: "Allow Over Delivery/Billing"
source_url: "https://docs.frappe.io/erpnext/allow-over-delivery-billing-against-sales-order-upto-certain-limit"
section: stock
---

# Allow Over Delivery/Billing

## Overview

When processing a Delivery Note, the system validates that item quantities match those in the Sales Order. If quantities are increased, a validation message regarding over-delivery or over-receipt appears.

## Item-Level Configuration

For sales scenarios where delivering more items than specified in the Sales Order is necessary, update the "Allow over delivery or receipt upto this percent" field in the Item master. This same setting applies to purchase transactions when creating Purchase Receipts or Purchase Invoices from Purchase Orders.

### Example
With an order of 100 units and an over-receipt tolerance of 50%, you can receive up to 150 units.

## Global Configuration

Set a company-wide tolerance limit through Stock Settings:

1. Navigate to `Stock > Setup > Stock Settings`
2. Configure the `Limit Percentage` value
3. Save the settings

This global setting applies to all items unless overridden at the individual item level. The tolerance affects both delivery note validation and invoice rate validation based on preceding transactions.
