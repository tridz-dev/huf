---
title: "Projected Quantity"
source_url: "https://docs.frappe.io/erpnext/projected-quantity"
section: stock
---

# Projected Quantity

**Projected Quantity represents the anticipated inventory level for an item, calculated by combining current stock with anticipated supply and demand factors.**

This metric serves as the foundation for inventory planning systems, helping determine when to reorder and what quantities to order while maintaining appropriate safety stock levels for unexpected demand fluctuations.

## Calculation Formula

The system computes projected quantity using this equation:

*Projected Qty = Actual Qty + Planned Qty + Requested Qty + Ordered Qty - Reserved Qty - Reserved Qty for Production - Reserved Qty for Subcontracting - Reserved Qty for Production Plan*

### Component Definitions

* **Actual Qty**: Physical inventory currently held in the warehouse
* **Planned Qty**: Quantities awaiting manufacture via submitted Work Orders
* **Requested Qty**: Stock requested through Material Requests, added upon submission and subtracted when corresponding Purchase Orders, Work Orders, or Stock Entries are generated
* **Ordered Qty**: Quantities purchased but not yet received via Purchase Orders
* **Reserved Qty**: Quantities committed to customer Sales Orders but not yet delivered
* **Reserved Qty for Production**: Raw materials allocated upon Work Order submission, decreasing when transferred to Work in Progress warehouse
* **Reserved Qty for Subcontracting**: Raw materials set aside for subcontracting Purchase Orders, reduced when transferred to Supplier Warehouse
* **Reserved Qty for Production Plan**: Raw materials reserved upon Production Plan submission, decreasing when materials are allocated to corresponding Work Orders

## Related Topics

1. [Warehouse](/erpnext/warehouse)
2. [Material Request](/erpnext/material-request)
