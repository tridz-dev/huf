---
title: "Stock Reposting Settings"
source_url: "https://docs.frappe.io/erpnext/stock-reposting-settings"
section: stock
---

# Stock Reposting Settings

## Limit timeslot for Stock Reposting

Activating the "Limit timeslot for Stock Reposting" option enables the system to run reposting during specified hours, which helps prevent deadlock issues that can occur during the reposting process.

## Limits don't apply on

This configuration allows reposting to run throughout the day without time restrictions, which is particularly useful when accounting for weekly off-days or other scheduling needs.

## Use Item Based Reposting

This feature accelerates reposting by skipping duplicate item and warehouse combinations, thereby improving overall system performance.

## Do reposting for each Stock Transaction

The system typically creates reposting records only when future transactions exist for the same item-warehouse pair. This setting removes that requirement, ensuring reposting records are generated for all backdated entries to address potential concurrency issues and maintain audit trails.

## Notify Reposting Error to Role

When reposting encounters errors, notifications can be configured to send to specific user roles rather than defaulting to system managers.

## Enable Parallel Reposting

The system can utilize multiple background workers to process stock repostings concurrently per item, provided Item-Based Reposting is enabled. The "No of Parallel Reposting (Per Item)" setting defines how many parallel workers execute repost operations—higher values may accelerate processing but increase system load.

## Note for usage

Reposting handles computationally intensive operations across thousands of entries. Best practices recommend limiting backdated entries to one month maximum, as longer date ranges risk failure due to time constraints (1500-second timeout) and resource limitations during business hours.

## Issue for Legacy Serial Numbers

Serial numbers created before Version 15 may display incorrect valuation rates during reposting when the same serial number undergoes multiple inward-outward cycles. The solution involves enabling "Do not fetch incoming rate from Serial No" to retrieve rates from the most recent inward transaction instead.
