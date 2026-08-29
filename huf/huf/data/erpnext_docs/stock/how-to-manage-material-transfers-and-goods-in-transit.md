---
title: "How to Manage Material Transfers and Goods in Transit"
source_url: "https://docs.frappe.io/erpnext/how-to-manage-material-transfers-and-goods-in-transit"
section: stock
---

# How to Manage Material Transfers and Goods in Transit

## Overview

Material transfers between warehouses involve tracking stock movement through an intermediate "in-transit" state. ERPNext handles this through stock entries that record both the outgoing movement and incoming receipt separately, ensuring accurate inventory counts at each location.

## Key Concepts

**Goods in Transit** represents inventory that has physically left one warehouse but hasn't yet arrived at its destination. This tracking method prevents counting errors and maintains visibility throughout the transfer process.

The workflow involves:
- **Outward Movement**: Stock leaves the source warehouse and enters transit
- **Transit State**: Inventory held separately from both locations
- **Inward Receipt**: Stock arrives and is added to the receiving warehouse

## Creating the Outward Transfer

To initiate a goods-in-transit transfer:

1. Navigate to **Stock Entry** and create a new entry
2. Set the **Stock Entry Type** to **Material Transfer**
3. In the items table, specify:
   - Source Warehouse (sending location)
   - Item and quantity to transfer
4. Enable the **Add to Transit** checkbox
5. Save and submit the entry

When Material Transfer is selected as the entry type, ERPNext displays the relevant goods-in-transit fields on the form.

## Receiving the Transfer

The receiving warehouse must create a corresponding entry to complete the transfer:

1. Create another Stock Entry with type **Material Transfer**
2. Select the outgoing transfer reference
3. Specify the **Receiving Warehouse**
4. Confirm receipt of items
5. Submit the entry to add stock to the receiving location

## Benefits of This Approach

Using goods-in-transit tracking provides several advantages:

- **Accuracy**: Neither warehouse claims the stock until physical receipt
- **Visibility**: Track inventory status between locations
- **Accountability**: Clear record of transfer responsibility
- **Reconciliation**: Simplifies period-end stock verification
- **Multi-location Support**: Works across warehouse networks, branches, and store locations

## Practical Considerations

This method works best when transfer times are predictable and receipt confirmation happens promptly. The system maintains separate accounting for items in transit, keeping warehouse totals accurate throughout the movement process.
