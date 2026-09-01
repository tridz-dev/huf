---
title: "Sell Items in Different Units of Measure"
source_url: "https://docs.frappe.io/erpnext/Selling-in-different-UOM"
section: selling
---

ERPNext enables selling identical items across multiple units of measure while maintaining a single stock unit. Here's the full article content:

## Before you begin

Confirm:

- The required [Units of Measure](/erpnext/unit-of-measure-uom).
- The Item's Stock UOM.
- Accurate conversion factors.
- UOM-specific [Item Prices](/erpnext/item-price) or a conversion-based pricing policy.
- Whether fractional quantities are allowed.

Changing a conversion factor affects how transaction quantity translates into stock quantity. Test it before use.

## Add an alternative UOM to an Item

1. Open the [Item](/erpnext/item).
2. Confirm the Stock UOM.
3. In the **UOMs** table, add the selling UOM.
4. Enter the Conversion Factor relative to one Stock UOM.
5. Save.

![The UOM conversion table on an Item.](https://novacompanies.m.frappe.cloud/files/selling-uom-item-conversion.png)

Example: if one Carton contains 10 Units and Unit is the Stock UOM, set the Carton conversion factor to 10.

## Create UOM-specific prices

Create one Item Price for each deliberately priced UOM:

1. Open Item Price.
2. Select the Item and selling Price List.
3. Select the UOM.
4. Enter the Rate.
5. Save.

![Item Prices for an Item and Price List.](https://novacompanies.m.frappe.cloud/files/selling-uom-item-prices.png)

Use separate prices when a carton has a negotiated price rather than exactly ten times the unit price.

Alternatively, enable **Price Not UOM Dependent** on the [Price List](/erpnext/price-lists) when ERPNext should derive the alternate-UOM price using the conversion factor.

## Sell in an alternative UOM

1. Create a [Quotation](/erpnext/quotation), [Sales Order](/erpnext/sales-order), [Delivery Note](/erpnext/delivery-note), or [Sales Invoice](/erpnext/sales-invoice).
2. Add the Item.
3. Select the highlighted pencil icon to open the complete row editor.
4. Select the UOM.
5. Confirm the Conversion Factor, Quantity, Stock Qty, and Rate.
6. Save or submit.

![The Sales Order Items table where the transaction UOM is selected.](https://novacompanies.m.frappe.cloud/files/selling-uom-sales-order.png)

The dot before an Item Code shows stock availability at a glance: green means in stock and red means out of stock.

## Understand transaction and stock quantities

If one Carton equals 10 Units:

| Transaction value | Result   |
| ------------------ | -------- |
| UOM                 | Carton   |
| Qty                 | 3        |
| Conversion Factor   | 10       |
| Stock Qty           | 30 Units |

Inventory reports and stock ledgers use the Stock UOM. The sales document can display the selected selling UOM.

## Fractional quantities

Use fractional quantities only when the UOM and Item allow them. For example, a service can be billed as 1.5 Hours, while a serialized laptop cannot usually be sold as 0.5 Unit.

Review UOM **Must be Whole Number** behavior and Item serialization or batching requirements.

## Troubleshooting

| Problem                                       | What to check                                                               |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| Alternative UOM is unavailable                | Add it to the Item's UOM table and save                                     |
| Stock Qty is incorrect                        | Correct the conversion factor                                               |
| No rate is fetched                            | Create an Item Price for the selected UOM or review Price Not UOM Dependent |
| Fractional quantity is rejected               | Check the UOM whole-number setting and Item constraints                     |
| Delivered stock differs from ordered quantity | Compare transaction Qty, UOM, Conversion Factor, and Stock Qty              |

## Frequently asked questions

### Can I keep stock in cartons and sell in units?

Yes. Choose the most appropriate Stock UOM and define the reciprocal business conversion accurately.

### Do I need a separate Item Price for every UOM?

Use separate Item Prices for deliberate UOM pricing. Use Price Not UOM Dependent for conversion-based pricing.

### Can the UOM change after submission?

Submitted stock and sales quantities should not be reinterpreted. Use the supported amendment or return workflow.

### Which quantity appears in the stock ledger?

Stock Qty in the Item's Stock UOM.

## Related topics

- [Unit of Measure](/erpnext/unit-of-measure-uom)
- [Item](/erpnext/item)
- [Item Price](/erpnext/item-price)
- [Price Lists](/erpnext/price-lists)
- [Sales Order](/erpnext/sales-order)
