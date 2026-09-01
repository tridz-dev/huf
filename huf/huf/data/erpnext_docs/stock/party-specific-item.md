---
title: "Party Specific Item"
source_url: "https://docs.frappe.io/erpnext/party-specific-item"
section: stock
---

# Party Specific Item

Party Specific Item is used to restrict which items, item groups, or brands can be used for a particular party. A party can be a **Customer** or a **Supplier**. This is useful when a business wants certain customers or suppliers to transact only in an approved set of items.

## When To Use Party Specific Item

- Use it when a customer should only be allowed to buy selected items, item groups, or brands.
- Use it when a supplier should only be used for selected purchase items, item groups, or brands.
- Use it when different parties have different product restrictions because of contracts, territory rules, compliance, or commercial agreements.
- Use it to reduce mistakes while creating sales and purchase transactions.

## Where To Find It

Open the Awesomebar and search for **Party Specific Item**, or go to **Selling > Item and Pricing > Party Specific Item**. The list view shows all configured party-specific item rules.

## How It Works

A Party Specific Item rule combines two decisions:

- **Party:** Select whether the rule applies to a Customer or Supplier, then choose the specific party.
- **Restriction Basis:** Choose whether the restriction is based on Item, Item Group, or Brand.

After the rule is saved, ERPNext can use it to control which items are allowed for that party in relevant sales or purchase transactions.

## Creating A Rule

1. Click **Add Party Specific Item**.
2. Select the **Party Type**: Customer or Supplier.
3. Select the **Party Name**.
4. Choose **Restrict Items Based On**: Item, Item Group, or Brand.
5. Select the corresponding value in **Based On Value**.
6. Save the document.

## Example

If **Mirae Fashion** is allowed to transact only in the item **Table**, create a Party Specific Item with:

- **Party Type:** Customer
- **Party Name:** Mirae Fashion
- **Restrict Items Based On:** Item
- **Based On Value:** Table

You can also create broader rules by selecting **Item Group** or **Brand** instead of a single item.

## Good Practices

- Use **Item** when the restriction is very specific.
- Use **Item Group** when the party is allowed to transact in a full product category.
- Use **Brand** when the restriction follows brand-level agreements.
- Keep the rules easy to audit by avoiding duplicate or overlapping restrictions for the same party.
- Test the rule in a sales or purchase transaction after saving it.

## Related Topics

- [Item](https://docs.frappe.io/erpnext/user/manual/en/item)
- [Customer](https://docs.frappe.io/erpnext/user/manual/en/customer)
- [Supplier](https://docs.frappe.io/erpnext/user/manual/en/supplier)
- [Item Group](https://docs.frappe.io/erpnext/user/manual/en/item-group)
- [Brand](https://docs.frappe.io/erpnext/user/manual/en/brand)
