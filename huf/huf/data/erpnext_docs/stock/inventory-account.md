---
title: "Inventory Account"
source_url: "https://docs.frappe.io/erpnext/inventory-account"
section: stock
---

# Inventory Account

In ERPNext, there are multiple ways to configure inventory accounts. Organizations can implement a "Warehouse-wise Inventory Account or use the default Inventory Account from the Company master, which is 'Stock In Hand.'"

## Warehouse-wise Setup

The system allows configuration at the warehouse level, as illustrated by the warehouse inventory account interface.

## Item-wise Inventory Account (Version 16+)

Starting from Version 16, the platform supports item-level inventory account configuration. To activate this feature, users must enable the "Enable Item-wise Inventory Account" option in the Company master settings.

Once activated, organizations can establish default inventory accounts through:
- Individual item master records
- Item Group level (for multiple items)
- Brand level (for multiple items)

This hierarchical approach allows flexibility without requiring individual configuration for every single item.

## Important Limitation

"Users can choose to use either item-wise or warehouse-wise inventory accounts, but not both." This constraint means organizations must select one approach rather than combining both methods simultaneously.
