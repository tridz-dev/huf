---
title: "Amending Sales Order after Submit"
source_url: "https://docs.frappe.io/erpnext/amending-sales-order-after-submit"
section: selling
---

After a [Sales Order](/erpnext/sales-order) is submitted, its core values are locked to protect the audit trail. ERPNext provides two ways to make a correction: use **Update Items** for permitted item-level changes, or cancel and amend the document when the change is broader.

## Before you begin

Check whether the Sales Order already has a submitted [Delivery Note](/erpnext/delivery-note), [Sales Invoice](/erpnext/sales-invoice), [Pick List](/erpnext/pick-list), or other linked transaction. Downstream documents determine which quantities and rates ERPNext can safely change.

Also confirm that you have permission to update or cancel submitted Sales Orders.

## Update item quantity, rate, or delivery date

Use this method when the submitted order is correct overall and only an allowed item value needs adjustment.

1. Open the submitted Sales Order.
2. Select **Update Items**, as highlighted.

![Update Items on a submitted Sales Order](https://novacompanies.m.frappe.cloud/files/update-items-button.png)

3. In the **Update Items** dialog, review the item row.
4. Use the highlighted pencil icon when you need to open the row editor.
5. Change the permitted **Delivery Date**, **Qty**, or **Rate**.
6. Select **Update**.

![Edit quantity and rate in the Update Items dialog](https://novacompanies.m.frappe.cloud/files/update-items-dialog.png)

ERPNext validates the change against linked transactions before saving it.

## Update rules and validations

| Change        | When it is normally allowed                          | Important limit                                                                         |
| ------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Quantity      | The order is undelivered or partly delivered         | The new quantity cannot conflict with quantity already delivered or otherwise fulfilled |
| Rate          | The order is not invoiced or is only partly invoiced | A submitted invoice can prevent changes that would conflict with its billed value       |
| Delivery Date | The order remains open and the revised date is valid | Linked fulfilment documents and permissions can restrict the update                     |

For a partly delivered order, keep the revised quantity at or above the quantity already delivered. For a partly invoiced order, keep the revised values consistent with the amount already billed. If ERPNext rejects the update, review the order's **Connections** tab and the validation message before deciding whether to amend the document.

## Cancel and amend the Sales Order

Use cancel and amend when **Update Items** does not cover the correction, such as changing the customer, company, currency, taxes, or another locked field.

1. Open the submitted Sales Order.
2. Review and handle linked documents first. You may need to cancel a dependent Delivery Note or Sales Invoice before ERPNext allows the order to be cancelled.
3. Select **Cancel** and confirm the action.
4. On the cancelled Sales Order, select **Amend**.
5. ERPNext creates a new draft linked to the cancelled order through **Amended From**.
6. Correct the required values, save, review, and submit the amended order.

The cancelled Sales Order remains in the audit trail. The amended draft receives a new document name based on the original series.

> Do not cancel a submitted order only to reduce an outstanding balance that the customer no longer wants. [Close the Sales Order](/erpnext/close-sales-order) instead.

## Choose the right action

| Situation                                                          | Action                                                           |
| ------------------------------------------------------------------ | ---------------------------------------------------------------- |
| Change an allowed item quantity, rate, or delivery date            | Update Items                                                     |
| Correct a locked header, customer, tax, currency, or company value | Cancel and Amend                                                 |
| Stop the remaining undelivered or unbilled balance                 | [Close](/erpnext/close-sales-order)                              |
| Fulfil or bill only part of the order now                          | [Partial Fulfilment](/erpnext/partial-fulfilment-of-sales-order) |
| Temporarily prevent further fulfilment                             | Hold                                                              |
| Reverse goods already delivered                                    | [Sales Return](/erpnext/sales-return)                            |

## Troubleshooting

### Update Items is not visible

Confirm that the Sales Order is submitted, not cancelled or closed, and that your role has the required permissions. An administrator can review [Role-Based Permissions](/erpnext/role-based-permissions).

### ERPNext will not accept the new quantity

The proposed quantity may be lower than a quantity already delivered, picked, manufactured, or otherwise reserved. Review linked documents in **Connections**.

### ERPNext will not accept the new rate

A submitted Sales Invoice may already use the original rate. Reverse or correct the invoice only when the accounting treatment requires it. Do not change submitted accounting records merely to force the order update.

### I cannot cancel the Sales Order

Cancel or unlink dependent transactions in reverse order where appropriate. For example, handle the Sales Invoice and Delivery Note before the Sales Order. Follow your organization's cancellation and accounting controls.

## Frequently asked questions

### Does Update Items create a new Sales Order?

No. It updates allowed values on the same submitted document and records the change in its version history.

### Does Amend overwrite the cancelled order?

No. ERPNext keeps the cancelled document and creates a linked draft.

### Can I reduce quantity after partial delivery?

Yes, provided the revised quantity does not fall below what has already been fulfilled and no linked transaction conflicts with the change.

### Should I amend an order when the customer cancels the remaining quantity?

Usually no. Complete the accepted delivery and billing, then close the remaining balance.

## Related topics

- [Sales Order](/erpnext/sales-order)
- [Close Sales Order](/erpnext/close-sales-order)
- [Short Close Multiple Orders](/erpnext/short-close-multiple-orders)
