---
title: "Managing Batch wise Inventory"
source_url: "https://docs.frappe.io/erpnext/managing-batch-wise-inventory"
section: stock
---

# Managing Batch wise Inventory

A collection of items sharing identical properties and characteristics can be consolidated into a single Batch. For instance, pharmaceutical products are organized by batch to facilitate tracking of manufacturing dates and expiration periods.

To set up batches for an Item, you must designate 'Has Batch No' as yes within the Item Master.

![Batch Item](/files/batchwise-stock-1.png)

You can generate a fresh Batch via:

`Stock > Documents > Batch > New`

Refer to [Stock batch](/erpnext/batch.html) for additional details.

For items designated as batch items, specifying the Batch No. in stock transactions (Purchase Receipt & Delivery Note) is required.

#### Purchase Receipt

When preparing a Purchase Receipt, you may create a new Batch or choose from existing Batch records. A single Batch can be linked to one Batch Item.

![Batch in Purchase Receipt](/files/batchwise-stock-2.png)

#### Delivery Note

Specify Batch details in the Delivery Note Item table. When a Batch item exists within a Product Bundle, you may also enter its Batch No. in the Packing List section.

![Batch in Delivery Note](/files/batchwise-stock-3.png)

#### Batch-wise Stock Balance Report

To view batch-wise stock balance information, navigate to:

Stock > Standard Reports > Batch-wise Balance History

![Batchwise Stock Balance](/files/batchwise-stock-4.png)
