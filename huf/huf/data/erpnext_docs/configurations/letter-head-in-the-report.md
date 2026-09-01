---
title: "Letter Head in the Report"
source_url: "https://docs.frappe.io/erpnext/letter-head-in-the-report"
section: configurations
---

# Letter Head in the Report

In reports, the Letter Head is retrieved from the Company master record.

To ensure the company's Letter Head appears correctly in reports, you must configure a default Letter Head in the Company master settings.

> Explore > Accounting > Company

![Letter Head](/files/using-print-format.png)

When no Letter Head is designated as default in a Company master, the system will use whichever Letter Head has its Default field enabled.

![Letter Head](/files/using-print-format-1.png)

For organizations operating multiple companies within a single ERPNext instance, verify that each Company has its default Letter Head configured in the Company master.

Once you have updated the Letter Head settings in the Company master, refresh your ERPNext instance and then review the print format of your report to confirm the changes have taken effect.
