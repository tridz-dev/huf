---
title: "Material Request"
source_url: "https://docs.frappe.io/erpnext/material-request"
section: buying
---

# Material Request

**A Material Request is a simple document identifying a requirement of a set of Items (products or services) for a particular reason.**

A Material Request can have the following purposes:

* **Purchase**: If the material being requested is to be purchased.
* **Material Transfer**: If the material being requested is to be shifted from one Warehouse to another.
* **Material Issue**: If the material being requested is to be Issued for some purpose like manufacturing.
* **Manufacture:** If the material being requested is to be produced.
* **Subcontracting:** If the material being requested is to be subcontracted to a vendor.
* **Customer Provided**: If the material being requested is to be provided by Customer. To know more about this, visit the [Customer Provided Item](/erpnext/customer-provided-items) page.

To access the Material Request list, go to:

> Home > Stock > Stock Transactions > Material Request

## 1. How to create a Material Request

1. Go to the Material Request list, click on Add Material Request.
2. Enter the Required By date.
3. Select the appropriate purpose from the list.
4. You can fetch Items from a BOM, Sales Order, or Product Bundle.
5. Select the Item and set the quantity.
6. Select the Warehouse for which Items are required.
7. You can change the Required By date for individual Items in this table.
8. Save and Submit.

### 1.1 Alternate ways of creating a Material Request

A Material Request can be generated automatically:

* From a [Sales Order](/erpnext/sales-order). While creating MR, user can choose to ignore or include Projected Quantity. Accordingly, Sales Order Items are fetched to MR.
* When the Projected Quantity of an Item in Stores (Warehouses) reaches a particular level.
* From your a [Production Plan](/erpnext/production-plan) to plan your manufacturing activities.

If your Items are inventory items, you must also mention the Warehouse where you expect these Items to be delivered. This helps to keep track of the [Projected Quantity](/erpnext/projected-quantity) for this Item.

> Info: Material Request is not mandatory. It is ideal if you have centralized buying so that you can collect this information from various departments.

### 1.2 Statuses

These are the statuses a Material Request can be in:

* **Draft**: A draft is saved but yet to be submitted to the system.
* **Submitted**: Document is submitted to the system.
* **Stopped**: If no more materials are needed the Material Request can be stopped.
* **Canceled**: The materials are not needed at all and the request is canceled.
* **Pending**: The Purchase/Manufacture is pending to complete the Material Request.
* **Partially Ordered**: Purchase Orders for some Items from the Material Request are made and some are pending.
* **Ordered**: All Items in the Material Request are ordered via Purchase Orders.
* **Issued**: The materials are issued using a Material Issue Stock Entry.
* **Transferred**: The required materials are transferred from one Warehouse to another using a Stock Entry.
* **Received**: The materials were ordered and have been received at your Warehouse using a Purchase Receipt.

## 2. Features

### 2.1 Items table

* **Barcode**: You can track Items using [barcodes](/erpnext/track-items-using-barcode).
* The Item Code, name, description, Image, and Manufacturer will be fetched from the Item master.
* **Scan Barcode**: You can add Items in the Items table by scanning their barcodes if you have a barcode scanner. Read documentation for [tracking items using barcode](/erpnext/track-items-using-barcode) to know more.
* The UoM, Conversion Factor, and Amount will be fetched. You change the Warehouse for which the material is being requested.
* Accounting details like Expense Account and Accounting Dimensions can be set for the Items.
* Page Break will create a page break just before this item when printing.

### 2.2 Setting Warehouses

* **Set Warehouse**: Optionally, you can set the Warehouse where the requested Items will arrive. This will be fetched into the 'For Warehouse' fields in the Item table rows.

### 2.3 More Information

In the 'Job Card' and 'Work Order' fields, it sets a reference from where the Material Request was generated.

### 2.4 Printing Details

#### Letterhead

You can print your Material Request on your company's letterhead. Read [Letter head documentation](/erpnext/letter-head) to learn more.

#### Print Headings

Material Request headings can also be changed when printing the document. You can do this by selecting a **Print Heading**. To create new Print Headings go to: Home > Settings > Printing > Print Heading. Know more [here](/erpnext/print-headings).

### 2.5 Terms and Conditions

In Sales/Purchase transactions there might be certain Terms and Conditions based on which the Supplier provides goods or services to the Customer. You can apply the Terms and Conditions to transactions to transactions and they will appear when printing the document. To know about Terms and Conditions, [click here](/erpnext/terms-and-conditions)

### 2.6 After Submitting

You can create the following documents:

* [Request For Quotation](/erpnext/request-for-quotation)
* [Purchase Order](/erpnext/purchase-order)
* [Supplier Quotation](/erpnext/supplier-quotation)

### 2.7 Automatically generate Material Requests

Material Requests can be generated automatically by enabling the setting in [Stock Settings](/erpnext/stock-settings#9-automatic-material-request) and setting the level in the [Item form](/erpnext/item#34-automatic-reordering). When the stock level dips below a certain quantity, setting a reorder will automatically create material requests for the Item.

### Note:

Material Request Purpose "Subcontracting" is newly added and only present in the develop branch of ERPNext. It will be there by default in the next major release i.e v16

A subcontracted Material Request enables the user to create a Subcontracted Purchase Order directly from the Material Request itself after submission.
