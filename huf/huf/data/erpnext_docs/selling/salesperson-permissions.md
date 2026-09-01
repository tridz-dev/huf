---
title: "Restrict Sales Users to Their Customers and Transactions"
source_url: "https://docs.frappe.io/erpnext/salesperson-permissions"
section: selling
---

## Overview

ERPNext enables sales teams to work within designated boundaries using User Permissions. Rather than relying solely on Sales Person records—which support targets and commissions—administrators must configure permissions to "limit which records of that type the user can access."

## Key Setup Steps

**1. Assign the Sales User Role**
Grant the sales employee the Sales User role through the User form's Roles & Permissions section. Additional roles should only be added when necessary for specific job functions.

**2. Create Customer Permissions**
Individual User Permissions must be created for each assigned Customer. This approach restricts access to those specific customers and their linked transactions (Quotations, Sales Orders, Delivery Notes, Sales Invoices) simultaneously.

**3. Handle Leads Separately**
Since unconverted Leads aren't yet Customers, "create a separate User Permission for each assigned Lead." This ensures salespeople can access only their own lead pipeline.

**4. Enable Apply To All Document Types**
Keep this setting active so a single Customer permission cascades across all transaction types. Disable it only when restricting access to one specific document type.

**5. Verify Access**
Use the "View Permitted Documents" feature to confirm the user sees only authorized records. Test with an actual non-admin account to validate the salesperson's actual experience.

## Scaling Considerations

For organizations with numerous customers divided geographically or by region, Territory-based permissions offer easier maintenance than individual Customer permissions. However, grouping masters should only replace individual permissions when they accurately reflect actual access boundaries.

## Related Settings

The system-wide "Apply Strict User Permissions" setting determines whether records with blank Customer or Territory links remain visible—important for reviewing legacy data before activation.
