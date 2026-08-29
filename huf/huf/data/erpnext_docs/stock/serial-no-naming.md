---
title: "Serial Number Naming"
source_url: "https://docs.frappe.io/erpnext/serial-no-naming"
section: stock
---

# Serial Number Naming

Serial numbers represent unique identifiers assigned to individual item units, enabling tracking of warranty and expiry information. Organizations typically serialize high-value assets such as machinery, computers, and specialized equipment.

To enable serialization, mark the **Has Serial No** checkbox in the Item master configuration.

## 1. Serializing Purchase Items

When vendors supply items with manufacturer-applied serial numbers, you can mirror those identifiers in ERPNext. During Purchase Receipt creation, scan or input the serial numbers for each item. Upon submission, the system creates corresponding Serial Number records.

For OEM-provided serial numbers, leave the Prefix field empty in the Item master to avoid conflicts.

If suppliers provide barcoded serial numbers, you can scan them directly into the Purchase Receipt form, streamlining data entry.

The system auto-generates Serial Numbers when submitting Purchase Receipts or Stock entries for serialized items. Generated identifiers populate automatically for each unit received.

## 2. Serializing Manufacturing Items

Define a Series pattern in the Item master to control Serial Number generation during production. The system automatically creates serial numbers following this pattern when production entries are submitted.

### 2.1 Serial No. Series

Serialized items allow you to specify a naming series for automatic generation purposes.

### 2.2 Production Entry for Serialized Items

Upon production entry submission, the system generates Serial Numbers automatically according to the series template defined in the Item master.
