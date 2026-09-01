---
title: "Packing List"
source_url: "https://docs.frappe.io/erpnext/packing-list"
section: selling
---

# Packing List

The **Packing List** functionality in ERPNext serves a specific purpose: it takes a [Product Bundle](/erpnext/product-bundle) ordered through a [Sales Order](/erpnext/sales-order) and breaks it down into individual stock components for fulfillment operations.

## Key Purpose

According to the documentation, "The Packing List in an ERPNext Sales Order shows the individual stock Items that must be delivered when the Customer orders a Product Bundle." This expanded view converts the bundled parent item into separate line items for accurate picking and packing.

## How It Works

The packing list generates automatically when you save a Sales Order containing a Product Bundle. The system multiplies each component's quantity by the ordered bundle quantity. For example, if a bundle contains 2 units of Item A and a customer orders 5 bundles, the packing list shows 10 units of Item A.

## Important Fields

| Field | Purpose |
|-------|---------|
| Parent Item | References the Product Bundle |
| Item Code | Individual stock component |
| Quantity | Total units needed |
| Warehouse | Stock location for fulfillment |
| Serial/Batch Number | Tracking for applicable items |

## Practical Workflow

The packing list remains internal to fulfillment operations. When creating a [Delivery Note](/erpnext/delivery-note), ERPNext uses these component details for stock movement while keeping the parent bundle on customer-facing documents like [Sales Invoices](/erpnext/sales-invoice).

## Troubleshooting

If the packing list appears empty, verify the Sales Order item is an active Product Bundle with valid components. Individual component warehouses can be modified as needed for multi-location fulfillment.
