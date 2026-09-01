---
title: "Batch"
source_url: "https://docs.frappe.io/erpnext/batch"
section: stock
---

# Batch

> "Allow Negative Stock has removed for Serial / Batch Items from version 15. So from version 15 users won't be able to make negative stock transactions for serial /batch items even though Allow Negative Stock has enabled in the Stock Settings."

The batch feature in ERPNext enables grouping multiple item units and assigning them a unique identifier. This functionality proves beneficial for managing expiry dates across multiple items or transferring them between warehouses as cohesive groups.

## Prerequisites

Before implementing batches, ensure you have:

- An Item created
- The "Has Batch No" checkbox enabled in the Item master

To activate serial and batch capabilities, navigate to Stock Settings and check the "Enable Serial and Batch No for Item" option.

## Creating a New Batch

If you haven't selected "Automatically Create New Batch" during Item creation, you'll need to create batches manually:

1. Access the Batch list and select New
2. Enter the Batch ID
3. Choose the associated Item
4. Save the record

Note: Once a transaction occurs with an item, its batch status cannot be modified.

## Batch Auto Creation

Enabling "Automatically Create New Batch" in the Item master allows batches to generate automatically during Purchase Receipt creation.

## Features

**Batch Management:**
- Use the Move button to transfer batches between warehouses
- Click Split to divide batches into smaller quantities, creating new batch records
- Track expiry status: batches display "Not Expired," "Expired," or "Not Set" depending on configuration

**Stock Transactions:**

When processing stock transactions involving batch items, always specify the Batch No. Batch IDs in transactions are filtered by Item Code, Warehouse, Batch Expiry Date, and warehouse quantity.

## Related Topics

- Serial Number
- Opening Stock Balance Entry For Serialized And Batch Item
- Managing Batch Wise Inventory
