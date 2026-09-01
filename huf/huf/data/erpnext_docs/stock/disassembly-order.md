---
title: "Disassembly Order"
source_url: "https://docs.frappe.io/erpnext/disassembly-order"
section: stock
---

# Disassembly Order

The 'Disassembly Order' feature in ERPNext serves to dismantle finished goods and restore components in working condition back to inventory. The system enables users to adjust the valuation rate of components when returning them to storage.

## Creating a Disassembly Order

To initiate a "Disassembly Order", locate a work order with either a **Completed** or **Closed** status. Select the create button, then choose "Disassembly Order" from the options.

Once you select the "Disassembly Order" button, ERPNext generates a stock entry configured with the type set to "Disassemble".

## Key Features

* Users have the ability to manually remove items that are damaged or defective
* The system automatically retrieves the standard rate from earlier transactions. Users may modify this basic rate for raw materials as needed.
