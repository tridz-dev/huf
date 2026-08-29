---
title: "Item Variants"
source_url: "https://docs.frappe.io/erpnext/item-variants"
section: stock
---

# Item Variants

**An Item Variant is a version of an Item with different attributes like sizes or colors.**

For example, a t-shirt available as an Item template can come in variations such as small, medium, large sizes and red, blue, or green colors. In ERPNext, the t-shirt serves as the Item template, while each combination—like a blue t-shirt in size small—represents an individual Item Variant.

This approach eliminates the need to create separate items for each size or color variation. Instead, users can manage all versions of a single product as variations of one parent Item.

## 1. Using Item Variants

Variants can be based on two things:

1. Item Attributes
2. Manufacturers

> Tip: Once an item template is created, when you update this template, all the variants are also updated accordingly.

### 1.1 Creating the Item Variant Template

1. To use Item Variants in ERPNext, create an Item and tick 'Has Variants' under Variants.
2. The Item then shall be referred to as a so-called 'Template'. Such a Template is not identical to a regular 'Item' any longer. For example, it (the Template) cannot be used directly in any transaction (Sales Order, Delivery Note, Purchase Invoice) itself.
3. Only the Variants of the Item (blue t-shirt in size small) can be practically used. Therefore it would be ideal to decide whether an item 'Has Variants' or not directly when creating it.
4. On selecting 'Has Variants' a table will appear. Specify the variant attributes for the Item in the table. In case the attribute has Numeric Values, you can specify the range and create intervals based on the increment values.

> Note: You cannot make Transactions against a 'Template'.

### 1.2 Creating the Item Variants Based on Item Attributes

To create 'Item Variants' against a 'Template' click on 'Create'. From there, choose whether to create a single variant or multiple. Single is simple where you create just one or more attributes and one Item will be created. When choosing multiple variants, tick the attributes and multiple items will be created. For example, if you choose Color: Red, Green and Size: Small, Medium, Large, 6 variants will be created.

To learn more about setting attributes, check out [Item Attributes](/erpnext/item-attribute).

### 1.3 Item Variants Based on Manufacturers

To set up variants based on Manufacturers, in your Item template, set "Variants Based On" as "Manufacturers". In this case, to create variants, click on Create > Make Variant. The system will prompt you to select a Manufacturer. You can also optionally put in a Manufacturer Part Number.

The naming of the variant will be based on the name (ID) of the template Item with a number suffix. For example, "Screwdriver" will have variant "Screwdriver-1".

## 2. Update Item Variants Based on Template

Go to: **Home > Stock > Items and Pricing > Item Variant Settings**. The fields displayed here will be copied over to the variants as well. By default, all fields are shown, delete any rows you don't want to be updated from the item template to the variants.

## 3. Related Topics

1. [Item Attribute](/erpnext/item-attribute)
