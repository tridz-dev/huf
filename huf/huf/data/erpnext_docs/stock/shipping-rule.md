---
title: "Shipping Rule"
source_url: "https://docs.frappe.io/erpnext/shipping-rule"
section: stock
---

# Shipping Rule

**Overview:** "Using Shipping Rule, you can define the cost for delivering the product to the customer or the supplier."

Shipping Rules help companies establish variable delivery charges based on transaction values. They enable businesses to offer reduced shipping on high-value orders while maintaining standard rates for smaller purchases.

## Creating a Shipping Rule

To access this feature, navigate to `Selling > Setup > Shipping Rule` or `Accounts > Setup > Shipping Rule`.

The setup process involves:

1. Opening the Shipping Rule list and selecting New
2. Assigning a descriptive label (examples: "Priority Shipping" or "Next Day Shipping")
3. Specifying required fields: Shipping Account, Cost Center, and Shipping Amount
4. Choosing a calculation method under "Calculate Based On" (options include Fixed, Net Total Quantity, or Net Total Weight; Fixed is the default)
5. Saving your configuration

## Key Capabilities

**Shipping Rule Conditions**

When selecting Net Total or Net Weight as calculation methods, a table appears for setting range values. Users input minimum and maximum thresholds and corresponding shipping amounts. The system applies charges only when transaction totals fall within specified ranges. Each Shipping Rule supports one calculation method exclusively.

**Country-Specific Application**

Administrators can restrict rules to particular countries by populating a country table. Without country specifications, rules apply globally. When countries are designated, charges activate only if the customer's location matches an entry in the rule.

**Implementation Example**

Shipping charges automatically populate in Sales Order transactions' "Taxes and Other Charges" section based on matching Shipping Rule criteria.
