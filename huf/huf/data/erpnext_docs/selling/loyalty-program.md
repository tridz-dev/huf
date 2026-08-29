---
title: "Configure Customer Loyalty Programs | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/loyalty-program"
section: selling
---

# Configure Customer Loyalty Programs | ERPNext Documentation

A Loyalty Program in ERPNext enables businesses to reward customers with points from sales transactions, which can be redeemed on future invoices. The system supports both single and multiple tier structures based on cumulative customer spending.

## Key Setup Requirements

Before implementation, organizations should verify eligible customers, customer groups, territories, company currency, loyalty expense accounts, and cost centers. Testing on a demo company is recommended before enrolling actual customers.

## Program Configuration

The creation process involves establishing program dates, selecting tier structure, restricting customer eligibility by group or territory, and configuring auto-enrollment preferences. As stated in the documentation, "A Loyalty Program awards points from submitted sales and lets eligible Customers redeem those points on later Sales Invoices."

## Tier Structure

Tiers define earning mechanics through collection factors (the amount required to earn one point) and minimum thresholds for tier qualification. The example provided indicates "with a Collection Factor of $100, an eligible $1,000 invoice earns 10 points."

## Redemption Setup

Key configuration includes conversion factors defining point monetary value, expense accounts for loyalty benefits, cost centers, and expiry duration in days. Organizations should maintain distinct earning and redemption rates.

## Point Management

Customers earn points through submitted sales invoices, with entries tracked in the Loyalty Point Entry ledger. Redemption requires enabling the loyalty points section within a sales invoice and specifying the point quantity to apply.

## Troubleshooting Resources

The documentation provides a comprehensive troubleshooting table addressing common issues including absent point earnings, unavailable redemption options, tier discrepancies, unexpected expiry, and accounting errors.
