---
title: "Short Close Multiple Orders"
source_url: "https://docs.frappe.io/erpnext/how-to-short-close-multiple-orders-in-erpnext"
section: selling
---

## Overview
This guide explains how to bulk close or reopen multiple Sales Orders in ERPNext. As the documentation states, "Closing is not deletion. The orders, completed deliveries, invoices, and payments remain available."

## Before Starting
Verify that selected orders meet these criteria:
- Each order is submitted and still open
- Customer-accepted quantities have been processed via Delivery Note or Sales Invoice
- Customer does not want remaining quantity fulfilled
- No draft, completed, cancelled, or already-closed orders were accidentally selected

## Closing Multiple Sales Orders

The process involves four steps:

1. Open the Sales Order list
2. Apply filters (Company, Customer, Delivery Status, or Billing Status)
3. Select checkboxes for orders to close
4. Choose **Actions > Close**

Closed orders cannot generate new Delivery Notes or Sales Invoices against outstanding quantities, though existing downstream documents remain linked and unchanged.

## Reopening Sales Orders

To resume fulfillment:

1. Filter the list to display **Closed** orders
2. Select the required orders
3. Choose **Actions > Re-open**
4. Verify outstanding quantities before creating new documents

## Partial Fulfillment Scenarios

When closing partially fulfilled orders, only the outstanding balance is affected. For example, if an order had 10 units with 8 already delivered, closing removes only the remaining 2 units from pending fulfillment. The 8 delivered units remain valid.

## Troubleshooting Common Issues

- **Close unavailable**: Confirm selection includes at least one Sales Order and your role has update permissions
- **Some orders not closed**: Mixed selections may include ineligible documents; filter by status and retry
- **Wrong orders closed**: Use **Actions > Re-open** to reverse the action

## FAQ Highlights

Bulk closing does not cancel linked Delivery Notes or Sales Invoices, only the outstanding balance. Orders from different customers can be closed together if eligible. Purchase Orders support equivalent bulk actions through the Purchase Order list.
