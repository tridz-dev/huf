---
title: "Landed Cost Voucher"
source_url: "https://docs.frappe.io/erpnext/stock-transactions-landed-cost-voucher"
section: stock
---

# Landed Cost Voucher

**Landed Cost is the final total cost associated with a product for it to reach the buyer's doorstep.**

Landed costs include the original cost of the item, complete shipping costs, customs duties, taxes, insurance, currency conversion fees, etc. All of these components might not be applicable in every shipment, but relevant components must be considered as a part of the landed cost.

## What is Landed Cost?

To understand landed cost better, consider this scenario: purchasing a washing machine requires researching prices. You might find a better deal from a distant store, but shipping costs could make the total expense higher than buying locally. The final cost—including delivery—determines the best choice. Similarly in business, identifying landed cost for items is crucial, as it helps determine selling prices and impacts profitability. Therefore, all applicable landed cost charges should be included in the item's valuation rate.

According to third-party logistics research, only 45% of respondents use landed cost extensively. The main obstacles include unavailability of necessary data (49%), lack of appropriate tools (48%), insufficient time (31%), and uncertainty about implementation (27%).

To access the Landed Cost Voucher list, navigate to: Home > Stock > Tools > Landed Cost Voucher

## 1. Prerequisites

Before creating and using Landed Cost Voucher, prepare the following:

- A **Purchase Receipt** or **Purchase Invoice** with *Update Stock* enabled. This is your original receipt of goods.
- A **Purchase Invoice** for the landed costs (e.g. Freight, Insurance, etc.)

The **Landed Cost Voucher** then decreases the costs recorded through the second **Purchase Invoice** and increases the stock value.

## 2. How to create a Landed Cost Voucher

1. Go to the Landed Cost Voucher list, click on New.
2. Select Receipt Document Type whether Purchase Invoice or Receipt. You can select multiple documents.
3. Select the specific Invoice or Receipt. The supplier name and Grand Total will be fetched automatically.
4. Click on the Get Items from Purchase Receipts button to fetch the item details from the Purchase Invoice/Receipt.
5. Select whether Distribute Charges Based On should be on quantity or Amount.
6. Enter the Expense Account and the Amount for Additional Costs in the Taxes and Charges table. The amount will be distributed equally based on the quantity or amount as per your selection.
7. Save and Submit.

In the document, you can select multiple Purchase Receipts/Invoices and fetch all items from those Purchase Receipts. Then you should add applicable charges in "Taxes and Charges" table. You can easily delete an item if the added charges do not apply to that item.

The added charges are proportionately distributed among all the items based their amount or quantity. If you selected based on the amount, the Item with the highest amount will be allocated the highest proportion of the charges. In case of quantity, Item with the highest quantity will be allocated most of the charges and the other Items will be allocated lesser amounts.

## 3. Related Actions

### 3.1 Adding Landed Cost in the Purchase Receipt itself

In ERPNext, you can add landed cost-related charges in "Taxes and Charges" table while creating Purchase Receipt (PR). You should add those charges for "Total and Valuation" or "Valuation" in the 'Consider Tax or Charge for' field. Charges which are payable to the same Supplier from whom you are buying the items should be tagged as "Total and Valuation". Otherwise, if applicable charges are payable to a 3rd party, it should be tagged as "Valuation". On submission of Purchase Receipt, the system will calculate the landed cost of all items, considering those charges. This landed cost will be considered to calculate the item's Valuation Rate (based on FIFO / Moving Average method).

However, during Purchase Receipt creation, all applicable charges might not be known. For example, transporters may send invoices months later, and customs duties are invoiced even later. Companies importing products/parts incur substantial customs costs with delayed invoicing. In these situations, "Landed Cost Voucher" provides a practical solution, enabling you to add charges retroactively and update purchased item valuations.

### 3.2 What happens on submission?

1. Valuation Rate of items is recalculated based on new landed cost.
2. If you are using "Perpetual Inventory", the system will post general ledger entries to correct Stock-in-Hand balance. It will debit (increase) corresponding "warehouse account" and credit (decrease) **Expense Account** mentioned in Taxes and Charges table. If items are already delivered, the Cost-of-Goods-Sold (CoGS) value has been booked as per the old valuation rate. Hence, general ledger entries are reposted for all future outgoing entries of associated items, to correct CoGS value.

### 3.3 LCV for Stock Entry

From version 16 of ERPNext, users can create a Landed Cost Voucher against a Stock Entry with the purpose set to 'Manufacture'. This feature allows users to include additional costs—such as electricity charges or rent—into the final valuation rate of the manufactured product.

### 3.4 LCV for Subcontracting Receipt

From version 16 of ERPNext, users can create a Landed Cost Voucher against a Subcontracting Receipt items which has been manufactured by the subcontractor. This feature allows users to include additional costs—such as freight charges, excise duty into the final valuation rate of the subcontracted product.

### 3.5 Vendor Invoices

You can link vendor invoices in the Landed Cost Voucher, and the system will ensure that the Landed Cost matches the total vendor invoice amount. Make sure the vendor invoices do not include any stock items.

## 4. Related Topics

1. [Delivery Trip](/erpnext/delivery-trip)
2. [Purchase Receipt](/erpnext/purchase-receipt)
