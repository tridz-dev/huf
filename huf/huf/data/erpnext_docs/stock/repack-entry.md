---
title: "Repack Entry"
source_url: "https://docs.frappe.io/erpnext/repack-entry"
section: stock
---

# Repack Entry

Repack Entry is used when bulk items need to be repackaged into smaller units. For instance, "item bought in tons can be repacked into Kgs."

## Key Points

1. The purchased item and repacked items must have different Item Codes
2. A Repack Entry can be created with or without a Bill of Material (BOM)

## Example Scenario

Consider buying boxes of spray paint in single colors (Green, Blue, etc.), then combining them into multi-color packs (Blue-Green, Green-Yellow combinations).

## Process Steps

### 1. Create New Stock Entry

Navigate to `Stock > Documents > Stock Entry > New Stock Entry`

### 2. Enter Item Details

- Select "Repack Entry" as the Purpose
- For input items (raw materials): specify only the Source Warehouse
- For output items (repacked goods): specify only the Target Warehouse and provide valuation details
- Update quantities for all selected items

### 3. Submit the Entry

Upon submission, the system reduces stock of input items from the Source Warehouse and adds repacked items to the Target Warehouse.
