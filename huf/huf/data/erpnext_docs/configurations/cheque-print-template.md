---
title: "Cheque Print Template"
source_url: "https://docs.frappe.io/erpnext/cheque-print-template"
section: configurations
---

# Cheque Print Template

**Cheque Print Template allows defining templates for bank cheques.**

Business involves making payment to various parties like suppliers and employees. Payment can be made in various modes like cash, NEFT or cheque. If you are making a payment via a cheque, you can also create a Print Format for printing Cheques from ERPNext based on the Payment Entry.

To access Cheque Print Template, go to: > Home > Accounting > Cheque Print Template

Using the Cheque Print Template you can generate a new Print Format for cheques. It will be created based on the cheque format provided by your bank.

A sample cheque:

![Sample Cheque](/files/sample-cheque.jpg)

## 1. How to create a Cheque Print Template

1. Go to the Cheque Print Template list, click on New.
2. You can set the position of various items in the cheque.
3. Save.

In the Cheque Print Template, for each value (say Payee, Date), exact coordinates are provided based on where that value should be printed on a cheque. Co-ordinates are provided in centimeters. Here is a representation the structure:

![Sample Cheque](/files/cheque-1.png)

### 1.1 New Format by Scanning

To speed up the creation of a new cheque printing format, you can upload a scanned image of the cheque. Considering the scanned image for the cheque, the system automatically updates co-ordinates for each value like party name, amount, date, the amount in words, etc.

### 1.2 New Print Format manually

"If the preview looks good, click on the **Create Print Format** button to create a new Print Format for printing the cheque." Based on the values provided in the Cheque Print Template, the system will auto-generate an HTML script for the cheque's Print Format.

You can manually provide the co-ordinate for each value based on where you want it to be printed on the cheque and customize with HTML/CSS.

#### Preview

Based on coordinates provided for all the values, a preview will be shown as to how the values will be printed on the cheque.

![Sample Cheque](/files/cheque-2.png)

### 1.3 Printing Cheques

The new print format generated for the cheque will be visible in the Payment Entry form. After creating the payment entry, you will be able to print transaction details on the cheque.

![Sample Cheque](/files/cheque-3.gif)

## 2. Related Topics

1. [Address Template](/erpnext/address-template)
2. [Terms and Conditions Template](/erpnext/terms-and-conditions)
