---
title: "Delivery from Sales Invoice"
source_url: "https://docs.frappe.io/erpnext/update-stock-option-in-sales-invoice"
section: stock
---

# Delivery from Sales Invoice

When items are delivered and invoiced simultaneously, you can generate delivery documentation directly within the Sales Invoice process. The Sales Invoice contains a field labeled **Update Stock**, positioned just before the Item table. Activating this checkbox will reduce inventory quantities from the designated Warehouse upon Sales Invoice submission.

Once Update Stock is enabled, the Sales Invoice Item section displays additional relevant fields including Warehouse, Serial No., Batch No., and Item valuation details.

When a Sales Invoice is submitted with this option active, the system processes both general ledger entries and stock ledger postings concurrently.
