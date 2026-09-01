---
title: "Fetch shipping charges based item's value or weight"
source_url: "https://docs.frappe.io/erpnext/can-we-fetch-shipping-charges-based-items-value-or-weight-in-po"
section: buying
---

# Fetch shipping charges based item's value or weight

The article explains how to automatically calculate shipping charges in a Purchase Order based on either an item's monetary value or its weight.

## Process Overview

To implement this feature, users should navigate to the **Shipping Rule list** and configure the "Calculate based on" setting to either "Net Total" or "Net Weight." After selecting the appropriate shipping rule conditions and populating the corresponding table, the system will automatically retrieve applicable shipping charges when creating a purchase order.

## Key Functionality

The setup ensures that "shipping charges will be fetched for the item based on item's weight or Value" during the PO creation process, streamlining cost calculations for order fulfillment.
