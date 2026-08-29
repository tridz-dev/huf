---
title: "Authorization Rule"
source_url: "https://docs.frappe.io/erpnext/authorization-rule"
section: configurations
---

# Authorization Rule

**Authorization Rule allows configuring a custom authorization / approval on a documents, based on conditions defined.**

Example: If a Sales Order's Grand Total exceeds $1,000, then it should be verified/submitted by the Sales Manager only, even if the Sales User has "Submit" permission.

On the same lines, you can define Authorization Rule based on the fields like Net Total, Grand Total, Discount % and specify who would be the document approver if the authorization condition is matched.

![Authorization Rule](/files/authorization-rule.png)

Let's consider a detailed example of an Authorization Rule to learn better.

Assume that the Sales Manager needs to authorize Sales Orders, only if it's Grand Total value exceeds 10,000. If the Sales Order value is less than 10,000, then even the Sales User will be able to submit it. This means that the Submit permission of Sales User will be restricted only up to Sales Order of Grand Total less than 10,000.

## 1. How to create an Authorization Rule

1. Go to the Authorization Rule list, click on New.
2. Select the transaction on which Authorization Rule will be applicable. This functionality is available for limited transactions only.
3. Enter the Authorized Value, etc. This depends on the field you selected in Based On.
4. Select Based On. Authorization Rule will be applied based on the value selected in this field.
5. Select Applicable Role. This is the role on which this Authorization Rule will be applicable. As per the example, it'll be Sales User.
6. To be more specific, you can also select Applicable To User if you wish to apply the rule to a specific Sales User, and not to all Sales Users.
7. Select Approving Role. This is the role that can approve forms over the Authorized value. As per our example, it is the Sales Manager.
8. You can also select a specific Sales Manager.
9. Save.

![Authorization Rule](/files/new-authorization-rule.png)

If the Sales User tries submitting the Sales Order of value higher than 10,000, then he will get an error message.

![Authorization Rule Validation Message](/files/authorization-rule-validation-message.png)

> If you wish to restrict Sales User from submitting Sales Orders, then instead of creating Authorization Rule, you should remove submit privilege for Sales User from [Role Permission Manager](/erpnext/role-based-permissions).

### Documents on which Authorization Rule can be applied

1. Sales Order
2. Purchase Order
3. Quotation
4. Delivery Note
5. Sales Invoice
6. Purchase Invoice
7. Purchase Receipt
8. Appraisal

### Fields on which Authorization Condition can be based on

1. Grand Total
2. Average Discount
3. Customer-wise Discount
4. Item-wise Discount
