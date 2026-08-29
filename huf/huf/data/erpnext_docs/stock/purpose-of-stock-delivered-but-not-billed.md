---
title: "Stock Delivered but Not Billed"
source_url: "https://docs.frappe.io/erpnext/purpose-of-stock-delivered-but-not-billed"
section: stock
---

# Stock Delivered but Not Billed

## Overview

The Stock Delivered but Not Billed account functions as an intermediary accounting mechanism. Rather than immediately recognizing expenses upon delivery, this adjustment account maintains a record of "the value of delivered items before a bill has been raised." This approach preserves the integrity of the sales accounting cycle.

At any given moment, this account's balance reflects items that have completed the delivery phase but remain unbilled.

## Operational Mechanics

**During Delivery Note Processing:**
When a Delivery Note is submitted, the warehouse's Stock In Hand account receives a credit while the Stock Delivered but Not Billed account is debited for the full inventory value.

**During Sales Invoice Processing:**
Upon Sales Invoice submission, the flow reverses—the Stock Delivered but Not Billed account is credited, and the Cost of Goods Sold account absorbs the corresponding debit.

## Setup Options

Organizations can enable this accounting treatment at the company level through the **Enable Stock Delivered But Not Billed** setting. Additionally, companies may elect to suppress this account's appearance in sales return transactions using the **Disable Stock Delivered but Not Billed in Sales Return** option.

## Handling Retroactive Adjustments

When backdated entries modify valuation rates on existing Delivery Notes, the system recalculates and automatically updates corresponding Sales Invoice entries through an internal reposting mechanism, ensuring consistency across both documents throughout the complete sales workflow.
