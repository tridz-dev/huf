---
title: "Pick List"
source_url: "https://docs.frappe.io/erpnext/pick-list"
section: stock
---

# Pick List

A Pick List is a document that indicates which items should be taken from your inventory to fulfill orders.

This proves particularly valuable for shippers managing substantial inventory or high order volumes. The system selects warehouses using FIFO (First-In-First-Out) methodology. For batched items, the warehouse closest to expiry is prioritized.

**Access location:** Home > Stock > Stock Transactions > Pick List

## 1. Prerequisites

Before creating a Pick List, prepare:

* Stock Item
* Warehouse

## 2. How to Create Pick List

### Basic Steps

1. Navigate to Pick List list and click New
2. Set the Company
3. Select the Purpose from these options:
   - **Delivery:** Add items from Sales Orders for shipment; creates Delivery Notes post-submission
   - **Material Transfer for Manufacture:** Pull raw materials from Work Orders; enables Stock Entry creation
   - **Material Transfer:** Select items from Material Requests; allows Stock Entry creation

4. Add items and quantities to the Item Locations table
5. Click **Get Item Locations** to populate warehouse details
6. **Parent Warehouse:** Restricts suggestions to warehouses under the selected parent
7. Review Item Locations containing warehouse info, serial numbers (for serialized items), and batch numbers
8. Save and Submit

### 2.1 Creating from Sales Order

1. Open a Sales Order
2. Select Create > Pick List
3. All necessary data auto-populates
4. Alternatively, use "Get Items" to display pending orders
5. Verify warehouse assignments in Item Locations
6. Save and submit after picking completion

**Important:** "Pick list can only be created for Sales Orders which has '% picked' < 100" and Delivery Notes require submitted Pick Lists.

### 2.2 Creating from Work Order

1. Open a Work Order
2. Click Create Pick List
3. Enter finished goods quantity (calculates required raw materials)
4. Review warehouse assignments
5. Save and forward to picking personnel
6. Submit after stock picking completion

**Important:** Only 'Not Started' or 'In Progress' Work Orders qualify; Stock Entries require submitted Pick Lists.

### 2.3 Creating from Material Request

1. Open a Material Request
2. Select Create > Pick List
3. Verify Item Locations table
4. Save and distribute to personnel
5. Submit upon completion

**Important:** Only 'Material Transfer' type requests work; Stock Entries require submission.

## 3. Features

### 3.1 Update Current Stock

The "Update Current Stock" button refreshes quantities and warehouses in Item Locations, accounting for inventory shifts. This button disappears once associated Delivery Notes or Stock Entries exist.

### 3.2 Barcode Scanning

Two checkboxes enhance scanning capabilities:

- **Scan Mode:** Streamlines verification by scanning barcodes to confirm correct item selection
- **Prompt Qty:** When enabled, prompts users to enter increment quantities rather than defaulting to 1

## 4. Pick Manually

Enabling the "Pick Manually" checkbox prevents the system from overriding user-selected batches upon saving, maintaining manual warehouse selections.

## 5. Related Topics

* Sales Order
* Work Order
* Material Request
