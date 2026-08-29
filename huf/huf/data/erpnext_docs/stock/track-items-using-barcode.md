---
title: "Track Items Using Barcode"
source_url: "https://docs.frappe.io/erpnext/track-items-using-barcode"
section: stock
---

# Track Items Using Barcode

A barcode represents data encoded as vertically spaced lines. Barcode scanners function as input devices similar to keyboards. When a scanner reads a barcode, the corresponding data displays on the computer screen at the cursor location.

## Item Master

To assign a barcode to an item, open the Item record. You can also add barcode information when creating new items initially.

Once the barcode field is populated in the item master, items become retrievable through barcode scanning. This functionality is restricted to these transaction types: Delivery Note, Sales Invoice, Purchase Receipt, and Stock Reconciliation.

### UOM Specific Barcode

Different barcodes can be assigned for various packaging formats of the same item, such as individual units versus boxes. When you select a UOM in the Item Barcode table, it auto-selects during scanning operations.

## Using Mobile Phone/Smartphone to Scan and Add Items

Users can access their ERPNext account via smartphone and scan barcodes to add items directly from the Item master interface.
