---
title: "Print Settings"
source_url: "https://docs.frappe.io/erpnext/print-settings"
section: configurations
---

# Print Settings

**In Print Settings you can set your printing preferences like Paper Size, default text size, whether you want to output as PDF or HTML, etc.**

Since ERPNext is a browser-based application, the actual print command is executed by the browser you're using.

To edit Print Settings, go to:
> Home > Settings > Print Settings

There are various configurations available in the Print Settings. Let's learn about them.

## 1. PDF Settings

### 1.1 PDF or HTML

When you email any document (like Sales Order/Invoice) from ERPNext, it is sent in the PDF or HTML format. "The file is sent in PDF by default." If you wish to send a document in the HTML format, just uncheck the option "Send Print as PDF".

### 1.2 Repeat Header and Footer in PDF

The letterhead is a master where you can define the standard Header and Footer which is appended to the document's Print Format. If this property is enabled, then Header and Footer are added to each page. If you don't want header and footer repeat on each page, just disable this setting.

### 1.3 PDF Page Size

"The default size for printing PDF pages is A4, and you can choose any size from the options defined here, including custom dimensions defined in millimeters."

## 2. Page Settings

### 2.1 Print With Letterhead

Enabling this property will automatically tick the Letter Head option when printing a document. Note that you need to either set Letter Head as default or select one in the transaction for it to appear in the print view.

### 2.2 Compact Item Print

Transactions like sales orders/invoices have a table detailing items bought or sold. It has multiple columns like Item Name, Description, UoM, Rate Amount, etc. If there are many columns in the Item table, then Print Format looks bit cluttered. You can improve the view of the table by enabling Compact Item Print.

"As per this setting, there will be only four columns in the Print Format, namely: Description, Qty, Rate, and Amount." The values of other columns (like name, description, image, serial nos. etc.) are concatenated in the Description column.

### 2.3 Allow Print for Draft

"The documents (mostly transactions) have two stages of authentication, Save and Submit." The saved documents are the first draft and not submitted to the system. Hence printing is restricted for the documents at this stage. However, if you wish to permit users to print documents at the Draft stage as well, enable this checkbox.

### 2.4 Always add "Draft" Heading for printing draft documents

Enabling this setting will also print "Draft" in the Print Format, thus indicating that document shared is not completely authenticated yet.

### 2.5 Allow Page Break Inside Table

If an item's description captures more than usual space of a page, then enabling this setting will split the item's details to the next page. Hence, a page break will be inserted between the Item Description, and the rest of the details will be pushed to the next page.

### 2.6 Allow Print for Canceled

"Canceled transactions are the ones which don't have any impact on the reports." If you wish to allow printing for the canceled transactions, then enable this setting. A transaction can be canceled only once it is submitted.

### 2.7 Print Taxes with Zero Amount

In the sales and purchase transactions, you can add apply multiple taxes on the item. By default, in the print format, only taxes which have some amount calculated are visible. If you wish to also print the tax which was not applied and has zero tax amount, enable this setting.

## 3. Network Printer / Print Server

You can enable print server by filling the print server IP and port. Then chose the default printer.

Before enabling this feature you have to install the `pycups` library.

You may need first to install `cups` library if is not already on your system.

For Debian OS Family:

```
sudo apt-get install libcups2-dev
```

For Red Hat OS Family:

```
sudo yum install cups-libs
```

After that, install `pycups` in the env using the command:

```
./env/bin/pip install pycups
```

This is executed from the `frappe-bench` directory.

## 4. Raw Printing

You can enable raw printing and print to many supported thermal printers. Read Raw Printing to know more.

## 5. Related Topics

1. [Print Format](/erpnext/print-format)
2. [Print Style](/erpnext/print-style)
3. [Print Headings](/erpnext/print-headings)
4. [Custom Translations](/erpnext/custom-translations)
