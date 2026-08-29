---
title: "Stock Entry Purpose"
source_url: "https://docs.frappe.io/erpnext/stock-entry-purpose"
section: stock
---

# Stock Entry Purpose

Stock Entry represents a stock transaction that serves multiple purposes within ERPNext. The system supports seven distinct types of stock entries, each designed for specific inventory operations.

## 1. Purpose: Material Issue

A Material Issue entry facilitates the removal of items from a warehouse. "On submission of Material Issue, stock of item is deducted from the Source Warehouse." This entry type is typically used for low-value consumable items such as office supplies or product consumables. Additionally, it can reconcile inventory for serialized and batched items.

## 2. Purpose: Material Receipt

Material Receipt entries bring stock into a warehouse. "This type of stock entry can be created for updating opening balance of serialized and batched item." Items purchased without a Purchase Order can also be received through this mechanism. The Item Valuation field becomes mandatory for stock valuation purposes.

## 3. Purpose: Material Transfer

This entry type manages the movement of inventory between warehouses, enabling inter-warehouse stock redistribution.

## 4. Purpose: Material Transfer for Manufacture

Raw materials move from storage to production departments (typically a Work-in-Progress warehouse) using this entry. "Items in this entry are fetched from the BOM of production Item, as selected in Work Order."

## 5. Purpose: Manufacture

Created from Work Orders, this entry tracks the complete production cycle. "On submission, stock of raw-material items are deducted from Source Warehouse, which indicates that raw-material items were consumed in the manufacturing process." The finished product is then added to the target warehouse.

## 6. Purpose: Repack

Repack entries handle bulk purchasing followed by repackaging into smaller units.

## 7. Purpose: Subcontract

"Subcontracting transaction involves company transfer raw-material items to the sub-contractors warehouse." This requires establishing a dedicated subcontractor warehouse for material transfers.
