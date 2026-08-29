---
title: "Partial Fulfilment of Sales Order"
source_url: "https://docs.frappe.io/erpnext/partial-fulfilment-of-sales-order"
section: selling
---

## Overview

ERPNext permits flexible order fulfillment where "a submitted Sales Order does not need to be delivered or billed in one transaction." Organizations can ship items across multiple delivery notes, create separate invoices, handle returns, and close unwanted balances while maintaining a single confirmed order as the reference document.

## Key Capabilities

**Multiple Delivery Notes**
Sales orders can be fulfilled through staged shipments. Users create delivery notes from the order, retain only lines for the current batch, adjust quantities as needed, then submit. ERPNext automatically recalculates the "% Delivered" metric after each submission.

**Separate Invoicing**
Billing can occur independently of physical delivery. Organizations create sales invoices from the order, select specific lines and quantities to bill, then submit. The "% Billed" percentage updates automatically. Multiple invoices can reference a single sales order without creating stock movements unless "Update Stock" is enabled.

**Service-Based Fulfillment**
Service companies can represent engagements as single-line orders and "use decimal quantities to record progress," invoicing 0.25 after 25% completion, 0.35 at the next milestone, and 0.40 upon finishing. This approach requires decimal-friendly units of measure and non-stock item configuration.

**Quantity Adjustments**
The "Update Items" function allows reducing ordered quantities when customers and sellers agree, preventing reductions below delivered, billed, picked, or produced amounts. The "Close" status preserves the original commitment while halting fulfillment expectations.

**Mixed Fulfillment Models**
Orders can combine warehouse-supplied items with drop-shipped items from suppliers, routing each through appropriate operational channels while maintaining the sales order as the commercial reference.

## Progress Tracking

Six status indicators track order progression:
- **% Delivered**: Net quantity through submitted delivery notes, adjusted for returns
- **% Billed**: Invoiced quantity or value, adjusted by credits
- **To Deliver and Bill**: Both incomplete
- **To Deliver**: Billing complete, delivery pending
- **To Bill**: Delivery complete, billing pending
- **Completed**: Both requirements fulfilled
- **Closed**: Balance intentionally closed

## Returns and Adjustments

Sales returns are created from delivery notes as return delivery notes using negative quantities, automatically restocking inventory and reducing net delivered percentages. Financial adjustments require separate credit notes against the relevant sales invoice. These actions address different ledgers independently.

## Related Resources

- [Sales Order](/erpnext/sales-order)
- [Delivery Note](/erpnext/delivery-note)
- [Sales Invoice](/erpnext/sales-invoice)
- [Sales Return](/erpnext/sales-return)
- [Drop Shipping](/erpnext/drop-shipping)
