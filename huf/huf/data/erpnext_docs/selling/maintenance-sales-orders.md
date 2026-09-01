---
title: "Maintenance Sales Orders"
source_url: "https://docs.frappe.io/erpnext/maintenance-sales-orders"
section: selling
---

# Maintenance Sales Orders

A Maintenance Sales Order documents an agreed maintenance service for a Customer, using the Sales Order workflow while enabling maintenance-related actions and allowing service invoicing without a stock delivery.

## Before you begin

Create the [Customer](/erpnext/customer), service [Item](/erpnext/item), and required serial-number or installation details. Confirm access to the maintenance documents used by your process.

## Create a Maintenance Sales Order

1. Open **Sales Order** and select **Add Sales Order**.
2. Select the Company and Customer.
3. Set **Order Type** to **Maintenance**.
4. Add the maintenance Item, quantity, rate, and service date.
5. Enable **Skip Delivery Note** when no stock delivery is needed.
6. Review taxes, payment terms, addresses, and terms.
7. Save and submit the order.

![A full-screen Maintenance Sales Order showing the Skip Delivery Note checkbox beside Order Type.](/files/sales-order-skip-delivery-note-full.webp)

Leave **Skip Delivery Note** disabled when the order includes goods that must be delivered through a [Delivery Note](/erpnext/delivery-note).

## Create maintenance documents

After submission, use the available **Create** actions. Depending on installed features and document state, these can include:

- a **Maintenance Schedule** to plan recurring service;
- a **Maintenance Visit** to record work performed;
- a **Sales Invoice** to bill the Customer.

Review generated documents and confirm the Customer, Items, dates, assigned personnel, serial numbers, and service details.

## Troubleshooting

### Skip Delivery Note is not visible

Confirm that **Order Type** is **Maintenance**. The checkbox is conditional.

### Maintenance actions are missing

Confirm that the order is submitted, required features are configured, and your role can create the target document.

## Frequently asked questions

### Can a Maintenance Sales Order include parts?

Yes, but use the delivery workflow for stock Items that physically leave your Warehouse.

### Is a Maintenance Schedule mandatory?

No. Use it when service must occur on planned dates. A one-time service may use only the documents required by your process.

## Related topics

- [Sales Order](/erpnext/sales-order)
- [Maintenance Schedule](/erpnext/maintenance-schedule)
- [Maintenance Visit](/erpnext/maintenance-visit)
