---
title: "Sales Order Type: Sales, Maintenance, Shopping Cart"
source_url: "https://docs.frappe.io/erpnext/sales-order-type"
section: selling
---

# Sales Order Type: Sales, Maintenance, Shopping Cart

A Sales Order represents a customer-confirmed commitment to purchase goods or services. ERPNext provides three distinct order types to guide different sales workflows.

## The Three Order Types

**Sales** is used for standard commercial transactions. As the documentation states, this is "the most common order type" and applies to scenarios ranging from stock items to services requiring billing or delivery.

**Maintenance** addresses after-sales scenarios. It's designed for "service, repair, support visits, or scheduled maintenance" where the focus is service delivery rather than product shipment.

**Shopping Cart** handles e-commerce transactions, originating from "website or e-commerce flow" rather than internal sales team creation.

## Key Workflows

Each type follows a distinct path:

- **Sales** typically flows: Quotation → Sales Order → Pick List/Material Request → Delivery Note → Sales Invoice
- **Maintenance** follows: Quotation → Sales Order → Maintenance Schedule/Visit → Sales Invoice
- **Shopping Cart** proceeds: Website Checkout → Sales Order → Payment/Pick and Pack → Invoice and Delivery

## Selection Criteria

The choice depends on the transaction's nature. Use Sales for standard fulfillment, Maintenance for scheduled service work, and Shopping Cart for online customer orders. Regardless of type, the Sales Order document serves as the central record confirming order details, pricing, and terms.
