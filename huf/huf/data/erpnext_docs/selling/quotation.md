---
title: "Quotation | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/quotation"
section: selling
---

# Quotation | ERPNext Documentation

A Quotation in ERPNext is a submittable sales transaction that documents products, services, quantities, prices, taxes, validity periods, and commercial terms offered to a Lead or Customer. It functions as a proposal that can be converted into a Sales Order following customer acceptance.

## Prerequisites

Before creating a quotation, ensure these records exist:

- A Lead or Customer
- Required Items with selling prices
- A selling Price List and Currency
- Applicable Sales Taxes and Charges Templates
- Terms and Conditions and Payment Terms (when needed)

## Creating a Quotation

The process involves:

1. Navigate to **Selling > Sales > Quotation**
2. Select **Add Quotation**
3. Choose Customer or Lead in the "Quotation To" field
4. Set the Date and Valid Till date
5. Confirm Order Type and Company
6. Add Items with Quantity, Rate, and Warehouse details
7. Include taxes, shipping, discounts, payment terms, and conditions as applicable
8. Review totals and save as draft

The quotation interface displays stock availability through color indicators (green for in-stock, red for out-of-stock). A pencil icon provides access to expanded item row editors for additional fields.

## Alternative Creation Methods

Quotations can be created from an Opportunity, which carries party and item details into the new document. Use "Get Items From > Opportunity" in draft quotations. For recurring quotes, leverage reusable masters like Price Lists, Item Prices, tax templates, payment terms, and terms templates rather than duplicating outdated transactions.

## Key Fields Explained

| Field | Purpose |
|-------|---------|
| Quotation To | Specifies whether the offer targets a Customer or Lead |
| Party | The selected Customer or Lead; fetches address and contact details |
| Valid Till | The final date the offer remains valid |
| Order Type | Identifies Sales, Maintenance, or Shopping Cart usage |
| Currency | The quotation's displayed currency; conversion rates apply if different from company currency |
| Selling Price List | Provides default item prices for the selected party and currency |
| Ignore Pricing Rule | Prevents configured Pricing Rules from modifying item prices or discounts |
| Item Code | The quoted product or service; fetches name, description, UOM, and price defaults |
| Quantity and UOM | The offered amount and its unit of measure |
| Rate | The unit price before multiplying by Quantity |
| Warehouse | The source warehouse for stock context and downstream mapping |
| Margin and Discount | Adjusts item rate by amount or percentage |
| Shipping Rule | Applies configured shipping charges per the selected rule |
| Incoterm and Named Place | Records agreed delivery responsibility and location for international trade |
| Payment Terms Template | Creates the proposed payment schedule |
| Print Heading | Displays alternative titles like "Proposal" without changing the document type |

## Pricing and Alternative Items

ERPNext retrieves defaults from Item and Item Price records, but the user remains responsible for all quoted rates. Apply item-level discounts or margins, or use Additional Discount for transaction totals. Specify whether additional discounts apply to Net Total or Grand Total.

To offer substitute products, add the alternative immediately after its primary item and enable "Is Alternative" in that row. Alternative items exclude themselves from totals. When creating a Sales Order from a quotation, ERPNext can prompt selection between alternatives.

## Taxes, Shipping, and Payment Terms

Select a tax template or manually enter rows in the Sales Taxes and Charges table. Use "Tax Breakup" to review components before sharing. A Shipping Rule calculates freight; an Incoterm documents delivery responsibility. A Payment Terms Template structures payments across deposits or milestones, displaying as a proposal that should align with the commercial agreement.

## Submission and Next Steps

Before submitting, verify: party details, validity date, items, quantities, rates, discounts, taxes, payment schedule, terms, delivery expectations, and print output. Submission locks the transaction as the approved version for sending.

After submission, use "Create > Sales Order" when acceptance occurs. If unsuccessful, select "Set as Lost" and document the reason. Cancel and amend submitted quotations requiring formal revision.

## Quotation Statuses

| Status | Definition |
|--------|-----------|
| Draft | Editable and unconfirmed |
| Open | Submitted offer awaiting an outcome |
| Ordered | A Sales Order has been created from it |
| Lost | The offer did not convert; reason recorded |
| Expired | The Valid Till date has passed |
| Cancelled | The submitted quotation was cancelled |

## Printing and Sharing

Review print previews before sending. Confirm that the selected Print Format, Letter Head, item images, terms, tax details, and Print Heading display correctly. A Print Heading changes only the displayed title without converting the record type.

## Common Questions

**Can I quote a Lead without creating a Customer?**
Yes. Select Lead in Quotation To and create the Customer when the party qualifies and your workflow requires customer transactions.

**Can I edit a submitted Quotation?**
Cancel and amend it for formal revisions. Avoid silently changing offers already sent to parties.

**Can I create a Sales Invoice directly from a Quotation?**
The standard path is typically Quotation → Sales Order → Delivery → Invoice. Follow your organization's approved transaction path.

**Why did an item rate change automatically?**
Check the Price List, Item Price, Pricing Rules, party details, quantity, date, currency, UOM, and whether "Ignore Pricing Rule" is enabled.

## Related Resources

- [Opportunity](/erpnext/opportunity)
- [Sales Order](/erpnext/sales-order)
- [Applying a Discount](/erpnext/applying-discount)
- [Adding Margin](/erpnext/adding-margin)
- [Selling in Different UoM](/erpnext/selling-in-different-uom)
