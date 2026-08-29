---
title: "Warehouse"
source_url: "https://docs.frappe.io/erpnext/warehouse"
section: stock
---

# Warehouse

A warehouse functions as "a commercial building for storage of goods" utilized by manufacturers, importers, exporters, wholesalers, and transport businesses. In ERPNext, the concept expands beyond physical warehouses to encompass "storage locations," including detailed hierarchical structures.

## Creating a Warehouse Structure

ERPNext supports nested warehouse organization following this pattern:

*Warehouse > Room > Row > Shelf > Bin*

To establish a warehouse:

1. Navigate to Home > Stock > Settings > Warehouse
2. Click New and enter a warehouse name
3. Designate a parent warehouse if needed
4. Enable 'Is Group' to allow sub-warehouses
5. Save your entry

The system automatically appends company abbreviations to warehouse names for quick company identification.

## Configuration Options

**Account Setting**: Assign a default account for warehouse transactions, enabling visibility in the Accounting Ledger.

**Warehouse Type**: Create classifications such as supplier warehouses, stock warehouses, or WIP warehouses for reporting and transaction purposes.

**Location Details**: Add billing and shipping addresses, plus contact information for warehouse managers.

## Post-Creation Actions

After saving, three reporting options become available:

- Stock Balance report showing quantity and valuation
- General Ledger displaying accounting transactions
- Non-Group to Group conversion for structural changes

## Advanced Features

**Tree View**: Switch to hierarchical display showing parent-child warehouse relationships.

**Perpetual Inventory Integration**: When enabled, each warehouse requires linking to a Chart of Accounts entry matching the warehouse name, capturing the monetary value of stored materials. Sub-locations typically reference their root warehouse's account to avoid per-shelf accounting complexity.

ERPNext maintains stock balances for each item-warehouse combination, enabling historical stock queries by specific date.
