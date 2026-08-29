---
title: "Introduction to Selling Module"
source_url: "https://docs.frappe.io/erpnext/selling"
section: selling
---

## Overview

The Selling module in ERPNext integrates customer records, quotations, sales orders, deliveries, invoices, payments, pricing, and sales reports into a unified workflow. This integration allows sales teams to progress from initial inquiries to confirmed revenue while enabling operations and finance teams to work from shared data sources.

## Pre-Implementation Setup

Before processing live sales, complete these foundational tasks:

1. Create customer records with billing and shipping addresses
2. Add products and services as items in the system
3. Configure a selling Price List and establish item prices
4. Review Selling Settings for transaction defaults and validations
5. Set up taxes, payment terms, warehouses, and user permissions

The documentation notes that implementations can begin modestly and expand controls as the sales process matures.

## Sales Cycle Variations

ERPNext supports four common sales process variations:

**Standard Goods Sale** — Best for distributors and manufacturers handling stocked goods. The workflow moves through Sales Order → Delivery Note → Sales Invoice → Payment Entry.

**Direct Invoice with Stock Update** — Ideal for retail and cash-and-carry environments. A single Sales Invoice simultaneously reduces inventory and bills customers.

**Service Sale Without Stock Delivery** — Designed for consulting, software, and project-based firms using non-stock service items. The process skips Delivery Notes entirely.

**Drop-Shipped Sale** — Suitable for online retailers and trading companies. A Sales Order triggers a supplier Purchase Order for direct customer delivery.

## Key Management Capabilities

The Selling module enables management of:

- Customer relationships, segments, and credit limits
- Quotations that convert to Sales Orders
- Sales Orders serving as fulfillment and billing references
- Invoices and receivable tracking
- Pricing rules, promotions, and loyalty programs
- Sales team performance and commission tracking
- Comprehensive sales analytics and reporting

## Best Practices

The documentation recommends converting related documents rather than recreating them, establishing clear naming conventions, defining approval authorities for pricing and credit changes, regularly monitoring fulfillment and receivables reports, and testing pricing rules before production deployment.
