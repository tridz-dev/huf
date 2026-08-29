---
title: "Purchase Order"
source_url: "https://docs.frappe.io/erpnext/purchase-order"
section: buying
---

# Purchase Order

A Purchase Order represents a binding contract with a supplier outlining a commitment to purchase specific items under agreed terms. Unlike Sales Orders directed to external parties, Purchase Orders serve as internal documentation within your organization.

### Prerequisites

Before creating a Purchase Order, establish:
- Supplier records
- Item master records

### Creation Process

Purchase Orders can be generated manually or automatically from Material Requests or Supplier Quotations. The standard workflow involves:

1. Accessing the Purchase Order list and creating a new entry
2. Designating the Supplier and setting required delivery dates
3. Selecting items with quantities (prices auto-populate from Item master if configured)
4. Applying applicable taxes
5. Saving and submitting the document

#### Warehouse Configuration

Set a default target warehouse for item delivery, which automatically populates item rows.

#### Fetching from Material Requests

Items populate automatically from open Material Requests when:
- A Supplier is selected
- Default Supplier is configured in Item settings
- A 'Purchase' type Material Request exists
- The "Get Items from open Material Requests" button is activated

### Key Features

**Address Management:** Billing and shipping addresses extract from Supplier records. GST details (for Indian operations) include GSTIN numbers and Place of Supply.

**Currency and Pricing:** Specify transaction currency and apply Price Lists. Pricing Rules can be overridden as needed.

**Subcontracting:** The "Supply Raw Materials" option facilitates subcontracting arrangements.

**Item Details:** The items table captures:
- Barcode scanning capability
- Automatic population of item name, description, and UOM
- Price List rates and last purchase rates
- Warehouse assignments
- Required By dates for partial deliveries
- Zero Valuation Rate allowances for sample items

**UOM Conversion:** Purchase UOM differs from Stock UOM. For example, materials arriving in boxes can be stored as individual units. Conversion factors adjust stock quantities accordingly.

**Taxes and Charges:** Additional supplier charges including shipping and insurance are recorded. Shipping Rules calculate costs based on delivery distance. Each tax head functions as an Account for accurate cost tracking.

**Discounts:** Apply discounts to entire Purchase Orders, calculated either on Grand Total (post-tax) or Net Total (pre-tax) amounts.

**Payment Terms:** Record partial payment schedules, such as deposits before shipment and final payment upon receipt.

**Terms and Conditions:** Supplier-specific terms display when printing documents.

**Print Settings:** Documents print on company letterhead with customizable headings. Grouping identical items consolidates display.

### Post-Submission Actions

After submitting, available actions include:

- **Update Items:** Modify or add items (received items cannot be deleted)
- **Status Changes:** Hold or Close the Purchase Order
- **Create Related Documents:**
  - Purchase Receipt
  - Purchase Invoice
  - Payment Entry
  - Journal Entry

### Related Documentation

- Request For Quotation
- Purchase Taxes and Charges Template
- Purchasing In Different Unit
- Amending Purchase Order After Submit
