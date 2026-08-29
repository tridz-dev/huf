---
title: "Create Supplier Quotation through Supplier Portal"
source_url: "https://docs.frappe.io/erpnext/how-to-create-a-supplier-quotation-through-the-supplier-portal"
section: buying
---

# Create Supplier Quotation through Supplier Portal

In ERPNext, there are two methods for creating Supplier Quotations: manual entry or through the Supplier Portal. Once suppliers gain access to the system, they can generate quotations independently.

## Prerequisites

Suppliers must meet two requirements:
* Registration as a Website User with the "Supplier" role
* Their Contact information must be associated with the Supplier document

## Process Overview

An existing Request for Quotation (RFQ) is necessary before a supplier can create a quotation. Here's how to complete the workflow:

**Step 1: Generate an RFQ**
Create a Request for Quotation in the system targeting the specific supplier (such as "MNO Suppliers").

**Step 2: Supplier Portal Access**
The supplier logs into their portal using their credentials and locates the RFQ awaiting their response.

**Step 3: Submit Pricing**
The supplier enters item rates and submits the RFQ through the portal.

**Step 4: Automatic Quotation Creation**
"Once the RFQ is submitted, a Supplier Quotation gets automatically created in the system against this RFQ."

**Step 5: Review and Finalization**
The generated Supplier Quotation initially appears in Draft status. After internal review, users can finalize submission, which updates the Supplier Portal accordingly.
