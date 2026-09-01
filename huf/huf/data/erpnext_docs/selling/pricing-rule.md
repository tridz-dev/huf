---
title: "Pricing Rule | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/pricing-rule"
section: selling
---

# Pricing Rule | ERPNext Documentation

## Overview
A Pricing Rule in ERPNext is a configuration tool that automatically adjusts commercial terms when specific conditions are met. As the documentation states, "A Pricing Rule tells ERPNext when to replace a standard rate, apply a discount or margin, or add a free product."

## Key Capabilities

The system supports several outcome types:
- **Rate replacement** - substitutes standard pricing
- **Discounts** - percentage or fixed-amount reductions
- **Margins** - additions over base rates
- **Free products** - promotional giveaways

## Important Configuration Elements

Rules can be restricted by numerous factors including item selection, customer/supplier designation, quantity thresholds, date ranges, warehouse location, and currency. The documentation emphasizes that "Check for overlapping Pricing Rules" before deployment to avoid unintended interactions.

## Usage Guidelines

The documentation recommends using Pricing Rules "for repeatable exceptions," while suggesting one-time adjustments be entered directly on transactions. For complex campaigns with multiple tiers, the system offers an alternative called Promotional Scheme.

## Advanced Features

The system supports priority hierarchies and optional rule stacking. A "Dynamic Condition" feature allows custom Python expressions when standard fields prove insufficient for specific requirements.

## Related Functionality

Pricing Rules integrate with Coupon Codes, Price Lists, and Loyalty Programs to create comprehensive pricing strategies within the ERPNext ecosystem.
