---
title: "Drop Ship"
source_url: "https://docs.frappe.io/erpnext/drop-shipping-in-erpnext"
section: selling
---

Drop shipping lets a Supplier deliver an item directly to your Customer. Your company creates the Sales Order and Purchase Order, but the goods do not pass through your warehouse. ERPNext links the two transactions so purchasing and sales teams can follow the same fulfilment.

![Drop-ship Sales Order with the customer, delivery date, supplier-delivered items, quantities, rates, and stock indicators.](/files/drop-ship-sales-order76e80b.webp)

## Before you begin

Create the [Customer](https://docs.frappe.io/erpnext/customer), Supplier, [Item](https://docs.frappe.io/erpnext/item), selling and buying prices, Customer shipping address, and Supplier contact details. The Item must have a Default Supplier or an appropriate supplier must be selected during purchasing.

## Create a drop-ship Sales Order

1.  Go to **Selling \> Sales \> Sales Order** and select **Add Sales Order**.
2.  Select the Customer, Company, and delivery date.
3.  Add the Item and Quantity.
4.  Open the item row with the pencil icon.
5.  Enable **Deliver to Customer** for the row.
6.  Select the Supplier and confirm the Customer shipping address.
7.  Save and submit the Sales Order.

![The highlighted pencil icon opens the complete Sales Order item row.](/files/drop-ship-item-pencil.webp)

The stock indicator before an Item Code is green when the item is in stock and red when it is out of stock. Drop shipping does not require the item to be received into your warehouse, but the indicator can still help users understand the item’s current availability.

![The item row with Supplier delivers to Customer enabled and Apex Devices selected as the Supplier.](/files/drop-ship-item-fields.webp)

![The Customer and company address information used for the drop-ship transaction.](/files/drop-ship-customer-address.webp)

## Create the Purchase Order

From the submitted Sales Order, select **Create \> Purchase Order**. In the dialog, select the Supplier and the drop-ship items, then create the Purchase Order.

Review the following before submission:

- **Is Subcontracted** should remain disabled unless the transaction is genuinely subcontracting.
- **Supplier** must be the party that will ship the goods.
- **Customer** and **Customer Address** must identify the final delivery destination.
- The items, quantities, rates, taxes, schedule dates, and terms must match the supplier agreement.

Submit the Purchase Order and send the approved document or instructions to the Supplier.

## Important fields and what they mean

| Field | What it means |
|----|----|
| Deliver to Customer | Marks the Sales Order item for direct delivery by a Supplier. |
| Supplier | The Supplier expected to fulfil that item. |
| Customer | The party receiving the goods. It is mapped to the Purchase Order for drop shipping. |
| Customer Address | The shipping destination printed or shared with the Supplier. |
| Schedule Date | The date by which the Supplier should deliver the item. |
| Warehouse | Usually not used to receive a drop-shipped item because it does not enter your stock. |
| Delivered By Supplier | Indicates that fulfilment is performed by the Supplier. Availability and wording can depend on the transaction and version. |

## Complete the sales cycle

A drop-ship Purchase Order does not create a stock receipt for your company. When the Supplier confirms delivery, use the actions available on the linked Sales Order or Purchase Order to record the delivery status according to your ERPNext version and process.

Create the [Sales Invoice](https://docs.frappe.io/erpnext/sales-invoice) for the Customer and the Purchase Invoice for the Supplier. Verify linked quantities so the Sales Order, Purchase Order, receivable, and payable all represent the same fulfilment.

If only part of an order is drop shipped, keep the remaining items on the normal warehouse fulfilment path. Each row can follow the appropriate route, but teams should verify the linked documents carefully.

## Returns and exceptions

If the Customer returns a drop-shipped item, coordinate the commercial and physical return with the Supplier. Create the appropriate return or credit documents for both sides. Because the goods did not enter your warehouse during the original delivery, do not create a warehouse receipt unless your return process actually brings them into your stock.

If the Supplier cannot fulfil the order, update or cancel the affected Purchase Order and resolve the Customer commitment on the Sales Order. Do not leave an open quantity without an owner or revised delivery date.

## Frequently asked questions

### Does drop shipping update stock?

Normally no. The Supplier delivers directly to the Customer, so the item does not pass through your warehouse.

### Can one Sales Order contain warehouse and drop-ship items?

Yes. Mark only the rows that the Supplier will deliver directly. Fulfil the other rows through Delivery Notes from your warehouse.

### Can different Suppliers fulfil different items?

Yes. Create the required Purchase Orders by Supplier and confirm that each item row is linked correctly.

### Why is the Purchase Order not available from the Sales Order?

Check that the Sales Order is submitted, the item row is marked for delivery to the Customer, a Supplier is selected or available, and the quantity is not already fully ordered.

### Who sends the invoice to the Customer?

Your company normally invoices the Customer. The Supplier invoices your company under the linked purchase transaction.

## Related topics

- [Sales Order](https://docs.frappe.io/erpnext/sales-order)
- [Purchase Order](https://docs.frappe.io/erpnext/purchase-order)
- [Delivery Note](https://docs.frappe.io/erpnext/delivery-note)
- [Sales Invoice](https://docs.frappe.io/erpnext/sales-invoice)
- [Sales Return](https://docs.frappe.io/erpnext/sales-return)
- [Drop Ship Between Subsidiary Companies](https://docs.frappe.io/erpnext/drop-ship-between-subsidiary-companies)
