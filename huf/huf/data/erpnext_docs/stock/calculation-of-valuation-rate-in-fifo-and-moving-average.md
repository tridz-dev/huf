---
title: "FIFO and Moving Average Calculation Difference"
source_url: "https://docs.frappe.io/erpnext/calculation-of-valuation-rate-in-fifo-and-moving-average"
section: stock
---

# FIFO and Moving Average Calculation Difference

## Overview

The valuation rate of an item is determined by calculating the total expenses needed to make a product available for sale, including factors like freight, labour, and raw material costs.

In ERPNext, the valuation rate depends on which method is selected for each item: either FIFO (First-In-First-Out) or Moving Average.

## Example Scenario

| Date      | Transaction | Qty | Unit Cost |
|-----------|-------------|-----|-----------|
| 1-4-2020  | Purchase    | 10  | 100       |
| 6-4-2020  | Purchase    | 20  | 120       |
| 10-4-2020 | Sale        | 15  | ?         |

## FIFO Method

Using this approach, inventory is consumed starting with the earliest purchases. For a 15-unit sale, 10 units come from the first transaction and 5 from the second:

(10 x 100) + (5 x 120) = 1,600

This leaves 15 units valued at **1,800**.

## Moving Average Method

This method recalculates item value each time inventory is purchased by combining the newly acquired cost with existing inventory value, then dividing by total quantity:

((10 x 100) + (20 x 120)) / 30 = 113.33

For the 15-unit sale:

15 x 113.33 = 1,700

This leaves 15 units valued at **1,700**.

## Key Insight

Though both methods result in identical final quantities, the stock valuations differ—1,800 versus 1,700—yet both approaches yield a combined total of 3,400.
