---
title: "Item"
source_url: "https://docs.frappe.io/erpnext/item"
section: stock
---

# Item

**An Item is a product or a service offered by your company.**

The term Item also applies to raw materials or components of products yet to be produced. ERPNext enables management of raw materials, sub-assemblies, finished goods, item variants, and service items.

ERPNext optimizes itemized management of sales and purchasing. For service-based businesses, create an Item for each service offered. Completing the Item Master is essential for successful ERPNext implementation.

To access the Item list: Home > Stock > Items and Pricing > Item

## 1. Prerequisites

Before creating and using an Item, establish these first:

- Item Group
- Warehouse
- A Unit of Measure if required

## 2. How to create an Item

1. Go to the Item list, click on new
2. Enter an Item Code; the name auto-fills the same as Item Code
3. Select an Item Group
4. Enter opening stock units and standard selling rate
5. Save

### 2.1 Item Properties

- **Item Name:** The actual name of your product or service
- **Item Code:** A short identifier for your Item. Keep Item Name and Item Code the same for small inventories to help users recognize items across transactions. For large inventories, use coding conventions (see Item Codification). Generate Item Codes using Naming Series via Stock Settings
- **Item Group:** Categorizes Items by criteria like products, raw materials, services, or sub-assemblies. Pre-configure Item Groups under Setup > Item Group
- **Default Unit of Measure:** The measuring unit for your product (Nos, Kgs, Meters, etc.). Store UOMs under Setup > Master Data > UOM, selectable using the % sign when creating Items

### 2.2 Options when creating an item

- **Disabled:** Prevents selection in any transaction
- **Allow Alternative Item:** Enables selecting alternative items when specific materials are unavailable during manufacturing
- **Maintain Stock:** Creates stock ledger entries for each transaction. Leave unchecked for non-stock items or services
- **Include Item in Manufacturing:** For raw materials used in finished goods. Keep unchecked for additional services used in BOMs
- **Valuation Rate:** Choose FIFO (first in - first out) or Moving Average for stock valuation
- **Standard Selling Rate:** Entering a value when creating an Item automatically creates an Item Price. Values entered after saving won't trigger automatic price creation
- **Is Fixed Asset:** Indicates a company Asset
- **Auto Create Assets on Purchase:** Automatically creates assets when purchasing this item through the Purchase Cycle
- **Allowance Percentage:** The percentage allowed for over-billing or over-delivering. Defaults to Stock Settings if unset
- **Uploading an Image:** Save the partially filled form first, then use the Change button on the Image icon to upload

For India:

- **HSN/SAC:** Harmonized System of Nomenclature (HSN) and Service Accounting Code (SAC) for GST purposes
- **Is nil rated or exempted:** For GST-covered Items with no tax applied
- **Is Non GST:** For items not covered under GST

## 3.1 Brand and Description

- **Brand:** Save multiple brands under Selling > Brand and pre-select when creating Items
- **Description:** Item description; text from Item Code is fetched by default

## 3.2 Barcodes

Barcodes enable quick scanning and addition in transactions. ERPNext supports:

- **EAN:** European Article Number (13-digit), used internationally and recognized by more POS systems
- **UPC:** Universal Product Code (12-digit), primarily used in USA and Canada

## 3.3 Inventory

- **Shelf Life In Days:** For Batched products, the number of days before unusability (e.g., medicines)
- **End of Life:** Date after which a single item becomes completely unusable in transactions and manufacturing
- **Warranty:** Track warranty periods; requires serialized Items. Delivery date and expiry period save in the Serial Number master

A warranty period is the timeframe in which purchased products may be returned or exchanged.

- **Weight UOM:** Unit of Measure for item weight (Nos, Kilo, etc.). May differ from purchase UOM
- **Weight Per Unit:** Actual weight per unit (e.g., 1 kilo of biscuits or 10 biscuits per pack)
- **Default Material Request Type:** Pre-selected in new Material Requests for this item
- **Valuation Method:** Select FIFO or Moving Average for stock valuation
- **Allow negative stock:** When checked, allows this item to go negative even if disabled in Stock Settings. Useful for low-value items

## 3.4 Automatic Reordering

When stock dips below a certain quantity, automatic reordering raises a Material Request. Must be enabled in Stock Settings. Purchase Manager and Stock Manager roles receive notifications.

- **Check in (group):** Warehouse group to check item quantity
- **Request for:** Warehouse to stock the reordered item
- **Re-order Level:** Quantity threshold triggering reorder, based on lead time and average daily consumption
- **Re-order Qty:** Units to reorder, balancing ordering and holding costs. May exceed reorder level based on supplier minimums and other factors
- **Material Request Type:** Whether the item is purchased, manufactured, or transferred between warehouses

The Material Request is created at 12 midnight based on the reorder level.

## 3.5 Multiple Units of Measure

Add alternate UoMs for Items. Example: sell in numbers but receive in kilos—add Kilogram as UOM with conversion factor 500 (500 Nos screws = 1 Kilogram).

## 3.6 Serial Numbers

Serial Numbers track warranty and returns. If a supplier recalls an item, this system helps identify affected units and manages expiry dates. Not necessary for small, low-value items like pens or erasers sold in thousands.

Avoid using serial numbers for products without warranties, major consumer durables, or recall risks.

Allow Negative Stock is disabled for Serial/Batch Items from version 15 onwards, preventing negative stock transactions even if enabled in Stock Settings.

## 3.7 Batches

A set of Items manufactured in batches associates expiry dates with specific batches.

- **Has Batch No:** Reveals batch number, expiry date, and sample retention options. Cannot activate if pre-existing transactions exist
- **Batch Number Series:** Prefix applied to batch numbers (e.g., 5x1SCR generates 5x1SCR00001)
- **Automatically Create New Batch:** Auto-creates batches in format AAAA.00001 if not specified in transactions
- **Has Expiry Date:** Batch numbers created according to expiry date, settable in the Batch master
- **Retain Sample:** Maintains minimum sample stock; requires Sample Retention Warehouse in Stock Settings
- **Has Serial No:** Similar to Batch Number Series; generates on transactions (e.g., AA generates AA00001)

When entering an Item Code in an inventory-requiring table, a pop-up dialog allows entering serial or batch numbers immediately.

Once marked as serialized, batched, or neither, this cannot change after Stock Entry creation.

## 3.8 Variants

An Item Variant is a different version of an Item (see Item Variants documentation).

## 3.9 Item Defaults

Define company-wide transaction defaults for this Item:

- **Default Warehouse:** Automatically selected in transactions
- **Default Price List:** Standard Selling or Standard Buying
- **Supplier:** Auto-selected for new purchase transactions if set
- **Default Expense Account:** Debits item costs here
- **Default Income Account:** Credits item sales income here
- **Default Cost Center:** Tracks item expenses

Add multiple rows for different companies.

## 3.10 Purchase, Replenishment Details

- **Default Purchase Unit of Measure:** UoM used in Purchase transactions
- **Minimum Order Qty:** Minimum quantity required for purchases; prevents proceeding with lesser quantities
- **Safety Stock:** Used in "Itemwise Recommended Reorder Level" report

Reorder Level = Safety Stock + (Average Daily Consumption × Lead Time)

- **Last Purchase Rate:** Rate from the most recent Purchase Invoice
- **Is Purchase Item:** Unchecking prevents using in purchase transactions
- **Is Customer Provided Item:** Checked if customers provide the item, received via Stock Entry > Material Receipt. Requires mandatory Customer field
- **Lead time days:** Days between ordering and warehouse delivery

## 3.11 Supplier Details

- **Delivered by Supplier (Drop Ship):** Check if the supplier delivers directly to the customer
- **Supplier Codes:** Track supplier-defined Item Codes. In Purchase transactions, Supplier Part No. auto-fetches for the supplier's reference

## 3.12 Foreign Trade Details

For items sourced internationally:

- **Country of Origin:** Sourcing country
- **Customs Tariff Number:** Reference number for customs agencies, usable in Delivery Notes

## 3.13 Sales Details

- **Grant Commission:** Allow commissions to Sales Persons and Sales Partners. Disable to exclude sales from commission calculations
- **Default Sales Unit of Measure:** UoM auto-fetched for sales transactions
- **Max Discount (%):** Maximum discount percentage allowed (e.g., 20% prevents discounts exceeding 20%)
- **Is Sales Item:** Unchecking prevents using in sales transactions

## 3.14 Deferred Revenue and Deferred Expense

Enable deferred revenue or expense, then set the Deferred Expense Account and deferral months. Example: yearly gym membership—upfront payment but service throughout the year. Gym owner sees deferred revenue; customer sees deferred expense.

## 3.15 Customer Details

Customers may identify Items with different codes, similar to Supplier Codes:

- **Customer Name:** Select a customer
- **Customer Group:** Auto-fetched based on selected Customer
- **Ref Code:** Customer's Item identifier, shown in created Sales Orders

## 3.16 Item Tax

Required only if an Item has different tax rates than standard Account rates. Create or choose an existing Item Tax Template. Example: if VAT 14% normally applies but an Item is exempted, select "VAT 14%" and set rate to "0". Also set a Tax Category for the Item.

## 3.17 Inspection Criteria

- **Inspection Required before Purchase:** Mandatory inspection before generating Purchase Receipt
- **Inspection Required before Delivery:** Mandatory inspection before generating Delivery Note
- **Quality Inspection Template:** Auto-updates in Quality Inspection tables; include criteria like Weight, Length, Finish, etc.

Quality Inspection supports Quick View without navigating to separate pages.

## 3.18 Manufacturing

- **Default BOM:** Default Bill of Materials for manufacturing this Item
- **Supply Raw Materials for Purchase:** Provide raw materials to subcontracted vendors using the default BOM
- **Manufacturer:** Manufacturer who produced the item
- **Manufacturer Part Number:** Manufacturer's assigned part number

## 3.19 Publishing Item on Website

From Version 16 onwards, the Webshop app separates from core ERPNext. Install Frappe's Webshop app to publish items on websites generated from your ERPNext account.

**Show on Website:** Choose whether to display this Item on your website via Action > "Publish in Website".

A Website Item record is created with additional details and published on the web view.

Website Item master fields include:

- **Weightage:** Items with higher weight display first. Supports very high numbers
- **Slideshow:** Display at page top (see Homepage in Website module)
- **Image:** Alternative to Slideshow
- **Website Warehouse:** Separate warehouse for online transactions, distinct from offline warehouses
- **Website Item Groups:** Select or create Item Groups for website classification
- **Set Meta Tags:** SEO support (see Web Page documentation)

## 3.20 Website Specifications

Configure additional item details:

- **Copy from Item Group:** Fetch Website Specifications from a chosen Item Group
- **Website Specifications:** Label and descriptions (e.g., 'Warranty: 1 year')
- **Website Description:** Appears on the item page
- **Website Content:** Create additional styling using Bootstrap 4 markup for the item page

## 3.21 Hub Publishing Details

The hub is a free online marketplace for Suppliers and Customers. Visit: https://hubmarket.org.

- **Publish in Hub:** Choose to publish on the free marketplace. Transactions seamlessly occur if both parties use ERPNext
- **Hub Warehouse:** Separate warehouse maintaining stock for hub transactions
- **Synced With Hub:** Sync item details with the hub during transactions

## 4. Video

## 5. Related Topics

1. Item Price
2. Item Codification
3. Item Variants
4. Item Group
5. Item Attribute
6. Item Valuation FIFO And Moving Average
