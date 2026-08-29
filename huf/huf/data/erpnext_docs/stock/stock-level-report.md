---
title: "Stock Level Report"
source_url: "https://docs.frappe.io/erpnext/stock-level-report"
section: stock
---

# Stock Level Report

The Stock Level report displays the quantity of stock items available in specific warehouses.

## Stock Projected Quantity Report

This report presents item and warehouse-specific stock levels, considering all stock transactions. Beyond the Actual Quantity, it includes:

1. **Actual Qty**: Available quantity in the warehouse
2. **Planned Qty**: Quantity with raised Work Orders pending manufacture
3. **Requested Qty**: Requested purchase quantity not yet ordered
4. **Ordered Qty**: Ordered purchase quantity not yet received
5. **Reserved Qty**: Ordered sale quantity not yet delivered
6. **Project Qty**: Calculated as follows

Projected Qty = Actual Qty + Planned Qty + Requested Qty + Ordered Qty - Reserved Qty

The planning system employs projected inventory to monitor reorder points and determine reorder quantities, while maintaining safety stock levels for unexpected demand fluctuations.

Effective control of projected inventory proves essential for identifying potential shortages and calculating appropriate order quantities.
