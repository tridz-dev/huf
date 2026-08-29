---
title: "Credit Limit"
source_url: "https://docs.frappe.io/erpnext/credit-limit"
section: selling
---

# Credit Limit

A Credit Limit in ERPNext represents "the maximum credit exposure your business allows for a Customer." When customers reach their limit, the system can prevent Sales Order or Sales Invoice submission until exposure decreases or authorized personnel approve an exception.

## How Limits Are Prioritized

ERPNext evaluates credit limits in this hierarchy:

1. **Customer** — Company-specific limit on individual customer records
2. **Customer Group** — Shared policy for customer classifications
3. **Company** — Final fallback for customers without specific limits

Note that "a value of 0 does not create an effective limit at that level," so explicit positive amounts must be set where controls should apply.

## Setting Limits

**For Individual Customers:**
- Navigate to the Customer's Accounting tab
- Add a row in Credit & Overdue Limits
- Select the Company and enter the limit amount
- Optionally enable bypass for Sales Orders

**For Customer Groups:**
- Access Selling > Settings > Customer Group
- Add company-specific rows in Credit & Overdue Limits

**For Company Fallback:**
- Open the Company record
- Enter the value in the Buying and Selling tab's Credit Limit field

## Key Configuration

The "Credit Manager" role in Accounts Settings determines who can approve exceptions when transactions exceed limits. Sales Orders reserve credit by default, while Sales Invoices check against outstanding receivables. The bypass option allows Sales Orders to proceed without credit reservation.

## Best Practices

- Record approved amounts at the most specific appropriate level
- Review limits periodically following payment behavior changes
- Restrict Credit Manager role membership to authorized personnel
- Combine credit limits with Payment Terms and Dunning for comprehensive receivables management
