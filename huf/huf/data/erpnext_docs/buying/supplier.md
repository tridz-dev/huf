---
title: "Supplier"
source_url: "https://docs.frappe.io/erpnext/supplier"
section: buying
---

# Supplier

Suppliers represent companies or individuals providing products or services. Access the Supplier list via: Home > Buying > Supplier > Supplier

### Creating a Supplier

1. Navigate to the Supplier list and select New
2. Input a supplier name
3. Choose a supplier group (Pharmaceutical, Hardware, etc.)
4. Save the record

Once saved, options for warning or preventing RFQs and POs become available after creating a Supplier Scorecard and conducting transactions.

### Features

#### Default Field Auto-Population

Setting "Default" fields like Default Bank Account and Default Payment Terms Template ensures these values automatically populate in future transactions.

#### Tax Details

The tax section includes:
- **Country:** Modify supplier location if international
- **Tax ID:** Supplier's tax identification number
- **Tax Category:** Links to Tax Rules for automatic template application during purchase transactions
- **Print Language:** Document printing language preference
- **Tax Withholding Category:** India-specific TDS category for Purchase Invoices
- **Disabled:** Removes supplier from active lists
- **Is Transporter:** Indicates transport service provision; reveals GST Transporter ID field when enabled
- **Internal Supplier:** Designates sister/parent/child company relationships

India-specific fields include GST Category and PAN (Permanent Account Number).

#### Purchase Invoice Flexibility

When "Purchase Order Required" or "Purchase Receipt Required" settings are configured in Buying Settings, individual suppliers can override these via "Allow Purchase Invoice Creation Without Purchase Order" or equivalent options.

#### Currency and Price Lists

Suppliers may operate in different currencies than your company. Selecting JPY for a supplier automatically applies that currency and exchange rate to purchase transactions.

Each supplier can have an associated Price List. When selected in purchase transactions, the linked Price List automatically fetches into the document. Access item pricing through Buying > Items and Pricing > Item Price.

#### Payment Terms and Supplier Blocking

- **Default Payment Terms Template:** Auto-selects for future purchases
- **Block Supplier:** Restricts invoices, payments, or both until a specified release date

Hold type options:
- Invoices: Prevents Purchase Invoices and Purchase Orders
- Payments: Prevents Payment Entries
- All: Applies both restrictions

Without a release date, ERPNext maintains the hold indefinitely.

#### Default Payable Accounts

Configure company-specific accounts for invoice payments. By default, the "Creditor" account handles payable entries. Customize by adding payable accounts in the Chart of Accounts and selecting them here.

For multiple companies, define company-wise payable accounts by adding rows in the Default Payable Accounts table.

#### Additional Information

The More Information section accommodates website details and supplementary supplier data. The "Is Frozen" option freezes accounting entries, with only designated role users permitted to modify frozen entries. This protects amended supplier information.

#### Address and Contacts

Addresses and contacts are stored separately, enabling multiple entries per supplier. After saving, create contacts and addresses for the supplier. The contact marked "Is Primary" auto-fetches when selecting the supplier in transactions.

#### Post-Save Dashboard Options

After saving, the dashboard displays creation options for:
- Request for Quotation
- Supplier Quotation
- Purchase Order
- Purchase Receipt
- Purchase Invoice
- Payment Entry
- Pricing Rule

The View button accesses the Accounting Ledger or Accounts Payable directly. A "Send GST Update Reminder" button requires a configured default email account.

### Adding Multiple Supplier Addresses

Multiple addresses (billing, shipping, warehouse, office locations) link to single suppliers through the Address doctype.

**Steps:**
1. Open the supplier via Buying > Supplier
2. In Addresses and Contacts, click New Address
3. Complete address details including Address Title, lines, city, state, and country
4. Optionally enable Is Primary Address and designate billing/shipping preferences
5. Verify the Links table shows Supplier as Link DocType with the supplier's name
6. Save

When creating Purchase Orders or Purchase Invoices, select the appropriate address from dropdowns. ERPNext applies selected addresses to document printing and regional information like taxes.

### Related Topics

- Supplier Quotation
- Supplier Scorecard
- Maintaining Supplier's Item Code In the Item Master
