---
title: "Migrate To Perpetual Inventory"
source_url: "https://docs.frappe.io/erpnext/migrate-to-perpetual-inventory"
section: stock
---

# Migrate To Perpetual Inventory

Perpetual Inventory Valuation is enabled by default in the system.

Users currently operating under periodic inventory valuation may transition to perpetual inventory valuation by following these steps.

## How to Migrate to Perpetual Inventory

1. **Sync Stock in Hand Account**: Ensure the Stock in Hand Account aligns with your actual warehouse stock value. Create a Journal Entry for any differences against an expense account (typically used in Purchase Invoices).

   Example: When perpetual inventory was disabled, expenses were booked through Purchase Invoices. Now create a Journal Entry to transfer existing stock value from the expense account to the stock in hand account:
   
   - Cr. Expense account ......... XXX
   - Dr. Stock in Hand account ... XXX

2. **Link Stock Accounts**: Before enabling Perpetual Inventory, ensure Stock Accounts are linked to existing Warehouses. Stock account configuration occurs at three levels:
   - Warehouse master
   - Parent Warehouse master
   - Default Stock in Hand Account in Company master (for single stock-in-hand account across all Warehouses)

3. **Update Stock Received but not Billed Account**: Create a Journal Entry to update the "Stock Received but not Billed" account, which tracks stock value for submitted Purchase Receipts awaiting Purchase Invoice creation. Reference the "Received Items Pending for Billing" report in Accounts.

   - Cr. Stock Received but not Billed ........... XXX
   - Dr. Expense Account (COGS) .................. XXX

4. **Configure Default Accounts**: Set up these default accounts per Company:
   - Stock Received But Not Billed
   - Stock Adjustment Account
   - Expenses Included In Valuation
   - Cost Center
   - Activate Perpetual Inventory

   Navigate to: **Home > Accounting > Company**

## Related Topics

- [Accounting Of Inventory Stock](/erpnext/accounting-of-inventory-stock)
- [Perpetual Inventory](/erpnext/perpetual-inventory)
