---
title: "Retaining Sample Stock"
source_url: "https://docs.frappe.io/erpnext/retain-sample-stock"
section: stock
---

# Retaining Sample Stock

**Sample stock represents a batch of items stored for potential analysis at a later time.**

Items designated for sample retention can include raw materials, packaging materials, or finished goods.

## Prerequisites

Establish the following components before implementing sample retention:

* [Item](/erpnext/item)
* [Batch](/erpnext/batch)
* [Warehouse](/erpnext/warehouse)

## Setting Sample Retention Warehouse in Stock Settings

Create a dedicated warehouse specifically for sample storage, keeping it separate from production operations.

### Enable Retain Sample in Item Master

"Retain Sample is based on Batch hence Has Batch No should be enabled first." Configure the retention feature by enabling the Retain Sample checkbox and specifying the maximum number of samples permitted per batch.

### Create Stock Entry

* When generating a [Stock Entry](/erpnext/stock-entry) classified as Material Receipt for items with sample retention enabled, designate the sample quantity during entry creation. A batch number must be selected for each item. The sample quantity cannot exceed the maximum established in the Item Master.

* Following submission, a "Make Retention Stock Entry" button becomes available. This enables creation of an additional Stock Entry to relocate samples from the current batch to the designated retention warehouse.

* Activating this button generates a new Stock Entry of type Material Transfer. "This entry is transfering your sample retention from your Target Warehouse (Stores) to the Sample Retention Warehouse." Review all details and submit the entry.

## Related Topics

1. [Warehouse](/erpnext/warehouse)
