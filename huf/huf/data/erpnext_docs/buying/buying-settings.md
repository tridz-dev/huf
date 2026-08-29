---
title: "Buying Settings"
source_url: "https://docs.frappe.io/erpnext/buying-settings"
section: buying
---

# Buying Settings

ERPNext provides configurable options to streamline and automate the purchasing workflow across multiple functional areas.

## Naming Series and Price Defaults

### Supplier Naming By
Organizations can choose how suppliers are identified in the system. Rather than using supplier names directly, you may prefer patterned identifiers like "SUPP-00001" by selecting the Naming Series option.

### Default Supplier Group
Set a default supplier classification when creating new supplier records—useful if most vendors fall into a single category.

### Default Buying Price List
Specify the default price list for new purchasing transactions. The standard option is "Standard Buying," though you can modify currency and country settings as needed.

### Action if Same Rate is Not Mentioned
When items lack rate information in purchase orders or material requests, the system can either:
- **Stop** the transaction until rates are specified
- **Warn** users while allowing the transaction to proceed

### Role Allowed to Override Stop Action
Configure which user roles can bypass the stop action when rate discrepancies occur.

## Transaction Settings

### Purchase Order Requirements
"Is Purchase Order Required for Purchase Invoice & Receipt Creation?" prevents direct invoice or receipt creation without a PO first. This requirement can be overridden per supplier in their master record. Exceptions exist for retail transactions or sample item receipt.

### Purchase Receipt Requirements
When enabled, "Is Purchase Receipt Required for Purchase Invoice Creation?" mandates receipts before invoicing—except for service items, which can be invoiced directly.

### Blanket Order Allowance
Set a percentage threshold for ordering beyond agreed blanket order quantities. A 10% allowance on a 100-unit order permits purchasing up to 110 units.

### Project Update Frequency
Control how often project records reflect total purchase costs.

### Maintain Same Rate Throughout Purchase Cycle
When enabled, this validates that item prices remain consistent across the purchase cycle. Actions can be set to either stop transactions or warn users when prices change.

### Item Duplication in Transactions
Uncheck "Allow Item to be added multiple times in a transaction" to prevent accidental duplicate line items, though quantity adjustments remain possible.

### Rejected Quantity Billing
Enable billing for rejected materials in purchase invoices. The companion option "Set Valuation Rate for Rejected Materials" creates accounting entries for rejected items instead of assigning zero valuation.

### Landed Cost Based on Invoice Rate
When "Maintain Same Rate Throughout the Purchase Cycle" is disabled, you can adjust product valuation to match purchase invoice costs rather than receipt costs, accounting for rate changes such as currency fluctuations.

### Last Purchase Rate Handling
The "Disable Last Purchase Rate" option prevents automatic rate inheritance from previous transactions.

### Exchange Rate Application
"Use Transaction Date Exchange Rate" applies the invoice date's exchange rate rather than the purchase order's rate for international transactions.

### Over Order Allowance
Specify the percentage by which material request quantities can be exceeded on purchase orders—for example, 10% allowance on a 100-unit request permits ordering 110 units.

## Subcontracting Settings

### Raw Material Backflushing
Choose whether materials are consumed based on the finished goods BOM or actual materials transferred for subcontracting.

### Automated Order Creation
Enable automatic draft subcontracting order generation upon purchase order submission when subcontracting is marked.

### Automated Receipt Creation
Automatically generate draft purchase receipts for service items upon subcontracting receipt submission.

### Over Transfer Allowance
Set the percentage threshold for transferring quantities beyond ordered amounts—a 10% allowance on 100 ordered units permits transferring 110 units.
