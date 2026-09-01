---
title: "Auto Email Reports"
source_url: "https://docs.frappe.io/erpnext/auto-email-reports"
section: configurations
---

# Auto Email Reports

**Auto Email Reports automatically sends reports for the selected document.**

You can setup **Auto Email Report** to send reports at regular intervals. These must be saved reports of any type (Report Builder, Script or Query Report).

You can find Auto Email Report at:

> Home > Settings > Auto Email Report

## 1. How to create an Auto Email Report

1. Go to the Auto Email Report list, click on New.
2. Select the Report for which you want to generate emails.
3. Select the user for which you want to create this report (permissions will apply for this user).
4. Set the Email Addresses to which you want this report to be emailed and the frequency of the report. Emails will be sent at midnight. The date will be repeated in case of weekly/monthly/yearly frequency.

5. Save.

You can test the report by clicking on "Download" or "Send Now". Here is an example of the email you will receive for a general ledger report.

## 2. Features

### 2.1 Filter Data

* **Send only if there is any data**: If enabled, emails will not be sent if there is no data in the report.
* **Only Send Records Updated in Last X Hours**: If set to 24, an email will contain only records updated in the last 24 hours.
* **No of Rows**: The number of rows to be sent in the email. The maximum is 500.

### 2.2 Report Filters

If your report has filters, you will be able to see them. Click on the table to edit it.

For example, if the email is on the report 'Project Billing Summary' select the Project. The date range here is the date range of the 'Project Billing Summary'.

### 2.3 Message

A message can also be added to be sent with the email report. For example, 'This is your monthly Project Billing Summary Report:'

You can also change the file format in which the report is created. The available options are HTML, XLSX, and CSV.

## 2. Related Topics

1. [Email Digest](/erpnext/email-digest)
2. [Document Follow](/erpnext/document-follow)
