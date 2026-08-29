---
title: "Item Where Used Report"
source_url: "https://docs.frappe.io/erpnext/item-where-used-report"
section: stock
---

# Item Where Used Report

The **Item Where Used** report displays master-data and product-structure connections for a specific Item. It answers questions such as "which BOMs or Product Bundles use this item?" while intentionally excluding transactional documents like Sales Orders, Purchase Invoices, Stock Ledger Entries, or Stock Entries.

## Filters

| Filter  | Required | Description                                                    |
| ------- | -------- | -------------------------------------------------------------- |
| Item    | Yes      | The Item to search for.                                        |
| Company | No       | Filters BOM-backed rows by Company.                            |
| Section | No       | Choose `Where Used` or `References`; leave blank to show both. |

## Sections

### Where Used

This section displays locations where the selected Item appears within another product or manufacturing structure.

| Reference Type               | Source                             |
| ----------------------------- | ----------------------------------- |
| BOM Component                | `BOM Item.item_code`               |
| Product Bundle Component     | `Product Bundle Item.item_code`    |
| BOM Secondary Item           | `BOM Secondary Item.item_code`     |
| Subcontracting Service Item  | `Subcontracting BOM.service_item`  |
| Subcontracting Finished Good | `Subcontracting BOM.finished_good` |

### References

This section displays related master references where the Item serves as the output, parent, template, or alternate item.

| Reference Type        | Source                                   |
| ---------------------- | ------------------------------------------ |
| BOM Output            | `BOM.item`                               |
| Product Bundle Parent | `Product Bundle.new_item_code`           |
| Item Variant          | `Item.variant_of`                        |
| Item Alternative      | `Item Alternative.item_code`             |
| Alternative For Item  | `Item Alternative.alternative_item_code` |

## Report Columns

| Column                      | Description                                                          |
| ----------------------------- | ------------------------------------------------------------------------ |
| Section                     | `Where Used` or `References`.                                        |
| Reference Type              | The type of usage or relationship found.                             |
| Document Type               | The linked DocType, such as BOM or Product Bundle.                   |
| Document                    | The linked document where the Item is referenced.                    |
| Related Item                | The parent, output, alternate, or related Item.                      |
| Matched Field               | The exact field that matched the selected Item.                      |
| Row                         | Child table row index, where applicable.                             |
| Qty / UOM                   | Quantity and UOM from the source row, where available.               |
| Stock Qty / Stock UOM       | Stock quantity and stock UOM from BOM rows, where available.         |
| Company                     | Company from the BOM, where applicable.                              |
| Default / Active / Disabled | Status metadata from the source document, where applicable.          |
| Details                     | Additional context such as secondary item type or linked BOM number. |

## Notes

- The report prioritizes master-data and intentionally excludes transactional usage
- The Company filter applies to BOM-backed rows
- Use the `Where Used` section for product-structure traceability
- Use the `References` section to find related definitions such as default/output BOMs, parent bundles, variants, and alternatives
