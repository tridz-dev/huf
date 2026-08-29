---
title: "Serial Number"
source_url: "https://docs.frappe.io/erpnext/serial-no"
section: stock
---

# Serial Number

> "Allow Negative Stock has removed for Serial / Batch Items from version 15. So from version 15 users won't be able to make negative stock transactions for serial /batch items even though Allow Negative Stock has enabled in the Stock Settings."

## Enabling Serial/Batch Features

To activate serial and batch functionality for items, navigate to Stock Settings and enable the 'Enable Serial and Batch No for Item' option.

## Overview

When an item is serialized, a Serial Number record tracks each individual unit. This system maintains details about the item's warehouse location, warranty information, and expiration dates. Users can also monitor supplier relationships and customer purchases associated with each serial number.

Serialized items require serial numbers to be entered individually in transaction documents. The Serial Number list is accessible via: Home > Stock > Serial No and Batch > Serial No

## Prerequisites

Before implementing serial numbers, prepare the following:

- Create an Item master record
- Enable 'Has Serial No' in the Item configuration

## Creating Serial Numbers

Serial numbers are typically generated automatically during stock transactions when 'Has Serial No' is enabled and a series format is defined in the Item master (for example: 'PB2L.#####').

### Manual Creation Process

1. Navigate to the Serial Number list
2. Click New
3. Input the serial number value
4. Enter the Item Code to auto-populate associated details
5. Save the record

**Important:** Once a serial number participates in any transaction, its assignment cannot be modified. Inventory changes only occur through formal stock transactions (Stock Entry, Purchase Receipt, Delivery Note, Sales Invoice).

### Key Notes

- Status updates reflect stock transaction activity
- Only "Available" status serial numbers can be delivered
- Auto-generation occurs from Stock Entries or Purchase Receipts
- If a series is defined in Item Master, the serial number field can remain blank

## Features

### Purchase/Manufacture Information

The originating document and supplier details appear here when applicable.

### Delivery Information

Customer information displays when generated from a Sales Order.

### Warranty/AMC Information

Expiration dates for warranty and Annual Maintenance Contract coverage can be recorded.

### Additional Details

Supplementary item-specific information is stored in the Serial No Details section.

## Related Topics

- Item Codification
- Item Variants
- Serial Number Naming
