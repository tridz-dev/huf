---
title: "Blanket Order"
source_url: "https://docs.frappe.io/erpnext/blanket-order"
section: selling
---

A Blanket Order in ERPNext records a long-term commitment to buy or sell specified items within an agreed period and at negotiated rates. It does not deliver, receive, bill, or pay for goods by itself. Instead, it becomes the reference for multiple downstream transactions as quantities are released over time.

![Blanket Order with the selling party, validity period, company, committed items, quantities, rates, and ordered quantities.](/files/blanket-order-overview.webp)

## Before you begin

Create the relevant [Customer](https://docs.frappe.io/erpnext/customer) or Supplier, [Items](https://docs.frappe.io/erpnext/item), currencies, and agreed rates. Confirm the total committed quantity and validity period before entering the agreement.

## Create a Blanket Order

1.  Go to **Selling \> Sales \> Blanket Order** and select **Add Blanket Order**.
2.  Set **Order Type** to **Selling** for a customer agreement or **Purchasing** for a supplier agreement.
3.  Select the Customer or Supplier.
4.  Enter the **From Date** and **To Date**.
5.  Add each Item, committed Quantity, Rate, and item-specific Terms and Conditions.
6.  Save and submit the Blanket Order.

![The highlighted pencil icon opens the complete Blanket Order item row.](/files/blanket-order-item-pencil.webp)

When editing an item row, select the pencil icon to open the complete row editor. This is useful when the row contains more fields than the table shows.

![The Blanket Order item row with committed quantity, negotiated rate, ordered quantity, and item-specific terms.](/files/blanket-order-item-row.webp)

## Important fields and what they mean

| Field | What it means |
|----|----|
| Order Type | Determines whether the agreement is for Selling or Purchasing. |
| Customer or Supplier | The party that made the commitment. The available field depends on Order Type. |
| From Date | The first date on which the agreement is valid. |
| To Date | The final date on which transactions should be created against the agreement. |
| Item Code | The product covered by the agreement. |
| Quantity | The total quantity committed for the validity period. |
| Rate | The negotiated unit rate used when transactions are created from the Blanket Order. |
| Ordered Quantity | The quantity already referenced by submitted downstream orders. Use it to monitor the remaining commitment. |
| Terms and Conditions | Item-specific commercial terms for the agreement. |

## Create transactions from a Blanket Order

After submission, use **Create** to generate the appropriate transaction:

- For a Selling Blanket Order, create a [Quotation](https://docs.frappe.io/erpnext/quotation) or [Sales Order](https://docs.frappe.io/erpnext/sales-order).
- For a Purchasing Blanket Order, create a [Purchase Order](https://docs.frappe.io/erpnext/purchase-order).

You can create multiple transactions from the same Blanket Order. ERPNext updates the ordered quantity as linked orders are submitted, making it easier to compare the commitment with actual releases.

You can also select a Blanket Order from an eligible downstream transaction. Always check the mapped item, remaining quantity, rate, schedule date, warehouse, taxes, and terms before saving.

## Monitor the agreement

Use the Blanket Order dashboard to open linked Quotations, Sales Orders, and Purchase Orders. Compare the committed Quantity with Ordered Quantity for each line. The outstanding quantity is the portion that has not yet been released into submitted orders.

A Blanket Order does not replace operational planning. Each Sales Order or Purchase Order still needs its own delivery schedule, warehouse, taxes, and approval before it moves through the standard sales or buying cycle.

## Amend an agreement

If a submitted Blanket Order contains an incorrect party, period, item, quantity, or rate, cancel and amend it according to your permissions and audit policy. Review linked orders before changing the source agreement. Do not create a replacement merely to hide an existing transaction history.

## Status and completion

A draft remains editable. A submitted Blanket Order can be used to create downstream transactions. A cancelled Blanket Order cannot be used for new releases.

ERPNext may not automatically close an agreement when its period ends or its quantity is fully ordered. Use the dates, ordered quantities, dashboard, and internal review process to identify completed or expired commitments.

## Video explaining Blanket Order

<div data-type="video-block" data-src="/files/blanket-order-smooth.mp4">

</div>

## Frequently asked questions

### Can one Blanket Order create multiple Sales Orders?

Y

es. Create each release as a separate Sales Order until the commitment is fulfilled or the validity period ends.

### Can I use a Blanket Order for purchasing?

Y

es. Select Purchasing as the Order Type, choose the Supplier, and create Purchase Orders from the submitted record.

### Does a Blanket Order reserve stock?

1.  It records a commercial commitment. Stock is reserved or moved only through the applicable downstream processes and settings.

### Why is Ordered Quantity not updated?

Check that the downstream order is submitted, linked to the correct Blanket Order and item row, and not cancelled.

### Can I use different rates in downstream orders?

The negotiated rate is mapped from the Blanket Order. Any change should follow your permissions and commercial approval process.

## Related topics

- [Sales Order](https://docs.frappe.io/erpnext/sales-order)
- [Quotation](https://docs.frappe.io/erpnext/quotation)
- [Purchase Order](https://docs.frappe.io/erpnext/purchase-order)
- [Terms and Conditions](https://docs.frappe.io/erpnext/terms-and-conditions)
- [Price List](https://docs.frappe.io/erpnext/price-list)
