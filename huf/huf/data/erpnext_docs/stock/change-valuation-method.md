---
title: "Change Valuation Method"
source_url: "https://docs.frappe.io/erpnext/change-valuation-method"
section: stock
---

# Change Valuation Method

ERPNext allows users to modify their inventory valuation approach, but with certain restrictions. Specifically, the system permits switching from FIFO to Moving Average, though the reverse transition is not supported for items that already have stock transactions recorded.

## Impact of Changing to Moving Average

When a user converts from FIFO to Moving Average methodology, subsequent outbound transactions will adopt the new Moving Average calculations. A notable consideration: if backdated entries are created following this change, the system will recalculate all subsequent transactions using the new method, which may alter the closing values shown in earlier records.

## Preventing Unintended Adjustments

To safeguard historical stock data from unexpected recalculations, users can implement a protective measure by establishing a "Stock Frozen Up To" date within the stock settings. This feature locks transactions from being reposted prior to the specified cutoff date.
