---
title: "Create a Sales Invoice without an Item Code"
source_url: "https://docs.frappe.io/erpnext/assistance-sales-purchase-between-companies"
section: selling
---

## Overview

This documentation covers inter-company drop shipping in ERPNext, where one company sells to a customer while another company supplies goods directly. The process combines drop shipping workflows with inter-company relationships.

## Initial Setup Requirements

Before implementing this workflow, ensure you have:

- Multiple companies configured within the same ERPNext instance
- An internal customer representing the purchasing company
- An internal supplier representing the selling company
- Proper company representation settings on both parties
- Configured items, warehouses, price lists, taxes, and inter-company accounts
- Appropriate permissions established for all companies involved

Review the "[Inter Company Invoices](/erpnext/inter-company-invoices)" documentation to understand how each company maintains separate accounting.

## Configuring Internal Parties

The setup process involves:

1. Creating a customer for the buying company
2. Enabling the **Is Internal Customer** flag and designating the **Represents Company**
3. Creating a corresponding supplier record
4. Enabling the **Is Internal Supplier** flag with the represented company selected
5. Saving both records

## Sales Order Creation

For the external customer:

1. Create a "[Sales Order](/erpnext/sales-order)" in the selling company
2. Add line items
3. Open individual item rows using the edit icon
4. Enable the **Drop Ship** option
5. Select the supplier representing the supplying subsidiary
6. Submit the order

**Note:** "stock availability in the selling Company's Warehouse does not replace Supplier" planning requirements.

## Purchase Order Generation

From your submitted sales order:

1. Select **Create > Purchase Order**
2. Choose the internal supplier
3. Verify the mapped customer delivery address and items
4. Confirm company, dates, rates, taxes, and terms
5. Submit the purchase order

The purchase order directs the supplying subsidiary to deliver directly to the external customer.

## Inter-Company Document Flow

After creating the purchase order, generate corresponding internal invoices following your inter-company transaction procedures. Finally, invoice the external customer from the selling company.

### Document Relationships

| Relationship | Document |
|---|---|
| External Customer owes selling Company | External Sales Invoice |
| Selling Company owes supplying subsidiary | Internal Purchase Invoice |
| Supplying subsidiary bills selling Company | Internal Sales Invoice |

**Important:** Tax and transfer-pricing requirements vary by jurisdiction and require qualified accounting guidance.

## Troubleshooting Guide

| Issue | Solution |
|---|---|
| Cannot select internal supplier | Verify Is Internal Supplier flag, Represents Company setting, permissions, and active status |
| Purchase Order uses incorrect company | Review internal party relationship and mapped company configuration |
| Missing customer address | Confirm sales order shipping address and drop-ship row configuration |
| Inter-company invoice not generated | Review reciprocal customer/supplier masters and inter-company settings |
| Stock moved in selling company | Verify Drop Ship is enabled and no delivery note was created |

## Frequently Asked Questions

**Does the selling company receive the goods?**

No. The supplier delivers directly to the external customer in the intended workflow.

**Are inter-company invoices required?**

Yes. Companies remain separate accounting entities despite sharing an ERPNext instance.

**Can partial drop shipping occur?**

Yes. Enable Drop Ship at the individual item level; remaining items follow standard warehouse processes.

**Does ERPNext set legal transfer prices?**

No. Organizations must configure internal rates and taxes per their policies and applicable regulations.

## Related Documentation

- "[Drop Ship](/erpnext/drop-shipping-in-erpnext)"
- "[Inter Company Invoices](/erpnext/inter-company-invoices)"
- "[Sales Order](/erpnext/sales-order)"
- "[Purchase Order](/erpnext/purchase-order)"
- "[Company](/erpnext/company)"
