---
title: "Making Custom Reports"
source_url: "https://docs.frappe.io/erpnext/making-custom-reports"
section: configurations
---

# Making Custom Reports

There are three kind of reports in ERPNext.

## 1. Report Builder

"Report Builder is an in-built report customization tool in ERPNext." It enables users to designate particular form fields for inclusion in reports, configure necessary filters, establish sorting preferences, and assign a custom name to the report.

## 2. Query Report

Query Report functionality relies on SQL to retrieve data from a database and present it in report format. While SQL queries can be authored through front-end interfaces like HTML, ERPNext cloud users face restrictions on this capability. The limitation exists because it prevents unauthorized users from accessing restricted reports by querying the database directly.

The Purchase Order Item to be Received report in the Stock module serves as a Query report example. Additional guidance on creating Query Reports is available in the Frappe Framework documentation.

## 3. Script Report

"Script Reports are written in Python and stored on server side." These handle intricate reporting requirements involving advanced logic and calculations. Since server-side implementation is required, customization through hosted accounts remains unavailable.

The Financial Analytics report within the Accounts module exemplifies a Script Report. The Frappe Framework documentation provides instructions for creating Script Reports.

> **Note:** "Dynamic Filter is available in Script Reports and Query Reports; however, not in the Report Builder."
