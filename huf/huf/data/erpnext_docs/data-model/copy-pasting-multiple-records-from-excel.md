---
title: "Copy Pasting Multiple Records From Excel"
source_url: "https://docs.frappe.io/erpnext/copy-pasting-multiple-records-from-excel"
section: data-model
---

# Copy Pasting Multiple Records From Excel

This feature allows you to transfer a sequence of records from an Excel sheet into a Child Table within ERPNext.

## Overview

"If you have a sequence of records saved in an excel sheet, that need to be mapped into a Child Table in ERPNext, the same can be done using this feature." For example, you might have item data in Excel that needs to populate the Items Child Table in a Sales Order.

## Steps to Copy Paste Records from Excel

* Organize your source data in Excel or a text editor with tab-separated columns.

* Select the records by dragging, then copy using the menu or Ctrl + C (Cmd + C).

  **Case 1:** The first column should contain the column header and corresponding data.

  **Case 2:** Without defined column headers, data maps to visible columns.

* Position your cursor in the target child table field and paste the data. "Unlike the import via upload file feature, this copy & paste feature will trigger field change events automatically."

## Performance Considerations

"For performance consideration, you should only paste less than or equal to 100 records at a time."
