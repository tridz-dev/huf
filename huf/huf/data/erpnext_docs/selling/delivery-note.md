---
title: "Delivery Note"
source_url: "https://docs.frappe.io/erpnext/delivery-note"
section: selling
---

## Overview

A Delivery Note documents the shipment of goods from a company's warehouse to a customer. As explained in the documentation, "A copy of the Delivery Note is usually sent with the transporter," and it serves to document items being shipped while updating inventory records. Creating a Delivery Note represents an optional step in the sales process—organizations may choose to create a Sales Invoice directly from a Sales Order instead.

## Prerequisites and Access

Before creating a Delivery Note, you should first establish a Sales Order. You can access Delivery Notes through: Home > Stock > Stock Transactions > Delivery Note.

## Creation Process

The typical workflow involves generating a Delivery Note from a submitted Sales Order by selecting Create > Delivery. Manual creation follows these steps:

1. Navigate to the Delivery Note list and click New
2. Retrieve customer and item details using 'Get Items from > Sales Order'
3. The system automatically populates UOM and rates
4. Save and submit the document

When fetching items from a Sales Order, "all the information about unshipped Items and other details are carried over from your Sales Order."

## Document Statuses

Delivery Notes can exist in these states:

- **Draft**: Saved but not yet submitted
- **To Bill**: Awaiting Sales Invoice creation
- **Completed**: Submitted with all items delivered
- **Return Issued**: All items have been returned
- **Cancelled**: The Delivery Note has been cancelled
- **Closed**: Manages partial fulfillment (e.g., delivering 15 of 20 ordered units)

## Key Features

### Partial Deliveries
Quantities can be modified when creating from a Sales Order, enabling staged deliveries across multiple Delivery Notes.

### Bulk Creation
"From a submitted Pick List, click on Create -> Delivery Note" to generate multiple Delivery Notes organized by customer and Sales Order.

### Address and Logistics
- Shipping Address: destination for customer items
- Contact Person: relevant contact information
- Transporter details: name, driver, distance, mode of transport

### Items Table Details
The items section tracks:
- Barcode and serialization data
- Warehouse sourcing information
- Batch and Serial Numbers
- Quality Inspection requirements
- Accounting dimensions

### Taxes and Charges
Tax information carries over from the Sales Order and can be configured through Taxes and Charges Templates and Shipping Rules.

### Packing and Shipping
For Product Bundles, the system automatically creates packing lists. Container shipments can be managed through Packing Slips, which cannot be created after submission.

## Post-Submission Actions

Upon submission, the system creates Stock Ledger Entries and updates inventory. The Dashboard provides options to create:
- Installation Notes
- Sales Returns
- Delivery Trips
- Sales Invoices

## Related Workflows

**Sales Returns**: Customers may return items after delivery, managed through the Sales Return process.

**Skipping Delivery Note**: Organizations can bypass Delivery Note creation entirely and proceed directly to Sales Invoice through Selling Settings configuration.
