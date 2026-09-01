---
title: "Inventory Dimension"
source_url: "https://docs.frappe.io/erpnext/inventory_dimension"
section: stock
---

# Inventory Dimension

Inventory dimensions in ERPNext represent a feature for monitoring stock using multiple custom parameters beyond the standard warehouse, batch, and serial number tracking. This functionality enables users to establish dimension-wise stock ledger and balance reports.

## Creating an Inventory Dimension

To establish a new inventory dimension:

1. Access the feature via Stock > Settings > Inventory Dimension
2. Select a reference document to serve as the custom dimension
3. Assign a dimension name for the system to generate associated custom link fields

## Application Scope

### Universal Application

When "Apply to All Inventory Document Types" is enabled, the custom dimension field appears across all inventory-related documents that contain batch and serial number fields.

### Selective Application

Users can limit dimensions to specific documents by disabling the universal application option. The feature also supports conditional application—for instance, different dimension names for various stock entry transaction types. An "Applicable Condition" field becomes available when universal application is disabled, allowing transaction-type-based rules.

## Automatic Value Population

The "Fetch Value From" capability allows automatic population of dimension values from parent-level fields. This eliminates manual entry repetition when a single value applies across multiple line items in a transaction.

## Transaction Implementation

Once created, the system automatically adds the custom field to relevant documents. Users can then select dimension values during transaction entry, with these selections recorded in resulting stock ledger entries.

## Negative Stock Prevention

When "Validate Negative Stock" is enabled, the system prevents transactions that would create negative stock positions for the specified dimension within a warehouse.

## Reporting Capabilities

Both Stock Balance and Stock Ledger reports support filtering by inventory dimensions, enabling visibility into dimension-specific available quantities.

## Stock Reconciliation Limitations

Stock reconciliation with inventory dimensions only supports entering opening values. The system prohibits quantity or valuation rate modifications through reconciliation when dimensions are involved.
