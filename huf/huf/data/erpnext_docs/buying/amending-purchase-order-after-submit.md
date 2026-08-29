---
title: "Amending Purchase Order after Submit"
source_url: "https://docs.frappe.io/erpnext/amending-purchase-order-after-submit"
section: buying
---

# Amending Purchase Order after Submit

Rate and Qty in Purchase Order can now be amended after Submit using the `Update Items` button.

To modify Rate and Qty in a Submitted Purchase Order, click the `Update Items` button. A dialog will appear allowing you to make the necessary changes.

## Important Validations and Use Cases

The Update Features functionality includes these checks:

- The system verifies whether the Purchase Order has associated Purchase Receipts and Purchase Invoices
- **Quantity updates**: Available for un-received and partially-received Purchase Orders. Cannot be updated if the Purchase Receipt is complete
- **Rate updates**: Available for un-invoiced and partially-invoiced Purchase Orders. Cannot be updated if a Purchase Invoice has been submitted
