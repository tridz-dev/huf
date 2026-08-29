---
title: "Stock Entry"
source_url: "https://docs.frappe.io/erpnext/stock-entry"
section: stock
---

# Stock Entry

**A Stock Entry lets you record Item movement between Warehouses.**

To access the Stock Entry list, go to:

> Home > Stock > Stock Transactions > Stock Entry

## Stock Entry Purposes

Stock Entries can be made for the following purposes:

- **Material Issue**: Outgoing material issued to someone inside or outside the company. Items are deducted from the Source Warehouse.
- **Material Receipt**: Incoming material being received. Items are added to the Target Warehouse.
- **Material Transfer**: Material moved between internal Warehouses.
- **Material Transfer for Manufacturing**: Raw materials transferred for manufacturing against a Work Order or Job Card.
- **Material Consumption for Manufacture**: Multiple consumption entries against a manufacturing Work Order.
- **Manufacture**: Material received from a Manufacturing/Production Operation.
- **Repack**: Original items repacked into new items.
- **Send to Subcontractor**: Material issued for sub-contract activity from a Purchase Order.

For detailed information, "visit this page" on stock entry purposes.

## 1. Prerequisites

Before creating a Stock Entry, establish:

- Warehouse
- Item

## 2. How to Create a Stock Entry

Stock Entries for Manufacturing are typically created from a Work Order. For manual creation:

1. Go to the Stock Entry list and click New
2. Select the Stock Entry Purpose
3. Default Source or Target Warehouses auto-fill if configured
4. Select Items and enter quantity
5. Basic rate fetches automatically with calculated amount
6. Save and Submit

"Source Warehouse" and "Target Warehouse" are both typically set for recording movement.

### 2.1 Additional Options

- **Work Order**: Displays for Manufacturing entries
- **Edit Posting Date and Time**: Allows date/time modification
- **Inspection Required**: For Quality Inspection before submission
- **From BOM**: Shows associated BOM for manufactured items

### 2.2 Stock Entry Type

Create custom Stock Entry Types with different names (like 'Scrap Entry') while maintaining the same purpose. This allows access control for specific user groups.

## 3. Features

### 3.1 The Items Table

Item details, rate, quantity, and valuation information display here. The 'Allow Zero Valuation Rate' option permits submission when item valuation rate is zero (samples or supplier agreements). Different Source and Target Warehouses can be set per item.

### 3.2 Scrap and Process Loss

- **Scrap Item**: By-products with valuation rates added to scrap warehouse. Users can set valuation rates manually.
- **Process Loss**: Reduces finished goods quantity without impacting stock. Costs distribute proportionally across finished items.

### 3.3 Additional Costs

For incoming entries, add related costs (shipping, customs, operating expenses). These affect item valuation rates.

To add additional costs:

1. Select the Expense Account for recording
2. Enter description and amount in the Additional Costs table

Costs distribute proportionally among receiving items based on basic amount, then add to item basic rates for final valuation.

### 3.4 Accounting Dimensions

Tag transactions by different dimensions like Projects to track costs. This follows standard cost tracking practices.

### 3.5 Printing Settings

#### Letterhead
Print Stock Entries on company letterhead.

#### Print Headings
Customize Stock Entry headings when printing by selecting a Print Heading.

### 3.6 More Information

- **Is Opening**: Marks opening stock entries
- **Remarks**: Additional item notes
- **Percentage Transferred**: Transfer percentage based on purpose
- **Total Amount**: Total transferred item amount

### 3.7 Perpetual Inventory

When perpetual inventory is enabled, additional costs post to the Expense Account specified in the Additional Costs table.

### 3.8 After Submitting

After submission, access stock ledger and accounting ledger from the dashboard.

## 4. Add to Transit

For two-step warehouse transfers, use the "Add to Transit" feature with Material Transfer entries.

Steps:
1. Create Material Transfer stock entry
2. Enable "Add to Transit" checkbox
3. Select source warehouse and Transit-type target warehouse
4. Add transfer items and submit

For destination warehouse entry, either:
- Open original entry and click "End Transit", or
- Create new entry, select "Get Items From" > "Transit Stock Entry"

The system fetches items with transit warehouse as source, requiring only target warehouse selection.

## 5. How to Update a Stock Entry

Cancel and amend submitted entries for updates.

## 6. Related Topics

1. Stock Entry Purpose
2. Stock Reconciliation
3. Opening Stock Balance Entry For Serialized And Batch Item
4. Work Order
5. Production Plan
6. Job Card
