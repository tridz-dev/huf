---
title: "Sales Partner Commission | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/sales-partner"
section: selling
---

# Sales Partner Commission | ERPNext Documentation

A Sales Partner represents an external reseller, dealer, agent, affiliate, or implementation partner helping generate business. ERPNext tracks sales attribution, commission calculations, targets, referrals, and performance metrics for these relationships.

## Key Distinction

"Use a Sales Person for internal sales-team contribution and incentives. Use a Sales Partner when the relationship is external and may require commission settlement through a Supplier."

## Setup Requirements

Before creating a Sales Partner, you'll need:

- A defined partner type (Reseller, Dealer, Affiliate, etc.)
- Default territory assignment
- Agreed commission rate and sales basis
- Contact and address details
- Fiscal year and monthly distribution for targets
- Supplier record if commission involves accounts payable

## Core Configuration

The master record captures four essential elements: partner name, classification type, geographic territory, and default commission percentage. Additional fields support website publishing, referral tracking, and performance targets.

## Commission Recording

Sales Partner fields integrate into transactions like Sales Orders, Delivery Notes, and Sales Invoices. Commission is calculated and reported but "does not automatically create an expense, payable, or payment."

## Performance Management

Targets allocate item-group-specific quantity or revenue goals by fiscal year. Referral codes track website traffic and e-commerce orders through campaign URLs containing partner parameters.

## Financial Settlement

Commission reporting summarizes transaction-level totals, but actual payment requires: a corresponding Supplier record, approved purchase invoices, tax treatment, and payment entries reconciled against commission reports.
