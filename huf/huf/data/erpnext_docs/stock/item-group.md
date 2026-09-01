---
title: "Item Group"
source_url: "https://docs.frappe.io/erpnext/item-group"
section: stock
---

# Item Group

**An Item Group is a way to classify items based on types.**

Depending on the product type, you can categorize items under respective fields. Service-oriented products go under the service Item Group, raw materials under Raw Material, and trading-only items under Trading.

To access the Item Group list, navigate to:

> Home > Stock > Items and Pricing > Item Group

## How to create an Item Group

1. Go to the Item Group list, click on New.
2. Select a group node under which you wish to create the Item Group, the default root is 'All Item Groups'.
3. Select 'Add Child' or click on the New button.
4. To make this child a category/group node, tick on Group Node.
5. Click on Create New.

**Note:**
- Nodes in different parts of the tree cannot have the same name.
- Child nodes get alphabetically arranged

### Delete an Item Group

1. Select the Item Group you want to delete.
2. Select 'Delete'.
3. Click on Yes.

## Features

To see the following options, click on an Item Group, click on Edit.

### Parent Item Group

You can change the parent Item Group of an item by choosing another one under General Settings.

### Defaults

- **Default Price List**: A default price list that determines Item Prices for this Item Group.
- **Default Warehouse**: The default Warehouse set in transactions for items in this group.
- **Default Buying/Selling Cost Centre**: The default Buying/Selling Cost Centre for items in this group.
- **Default Expense/Income Account**: The default accounts for items in this group.
- **Default Supplier**: This supplier will be chosen in purchase transactions by default for items in this group.

### Item Tax

A default item tax template applies to all items in this group. A Tax Category can also be selected.

### Website Settings

- **Show in Website**: Items belonging to this group display on your website under the Item Group.
- **Weightage**: The weight for Item Groups; higher weights appear first.
- **Slideshow**: A slideshow for the Item Group.
- **Description**: Appears on the Item Group page.
- **Website Specifications**: Labels and descriptions for an item group.
