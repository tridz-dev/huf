---
title: "Delivery Note"
source_url: "https://docs.frappe.io/erpnext/delivery-note"
section: stock
---

# Delivery Note

**A Delivery Note is made when a shipment is shipped from the company's Warehouse to the customer.**

A copy of the Delivery Note is usually sent with the transporter. The Delivery Note contains the list of Items that are sent in the shipment and updates the inventory. The Delivery Note is an optional step and a Sales Invoice can be created directly from a Sales Order.

To access the Delivery Note list, go to:

> Home > Stock > Stock Transactions > Delivery Note

## Prerequisites

Before creating and using a Delivery Note, it is advised that you create the following first:

- Sales Order

> Note: From version-13 onwards we have introduced immutable ledger which changes the rules for cancellation of stock entries and posting backdated stock transactions in ERPNext. Learn more here.

## How to create a Delivery Note

The entry of the Delivery Note is very similar to a Purchase Receipt. It is usually created from a "Submitted" Sales Order (that is not shipped) by clicking on Create > Delivery.

To create a Delivery Note manually (not recommended), follow these steps:

1. Go to the Delivery Note list, click on New.
2. The Customer and Item details can be fetched by clicking on 'Get Items from > Sales Order'.
3. The UOM and Rates will be fetched automatically.
4. Save and Submit.

To fetch Items from a Sales Order, click on Get Items from > Sales Order. This will open a popup from where you can search for Sales Orders and select one.

You will notice that all the information about unshipped Items and other details are carried over from your Sales Order if you create the Delivery Note from there.

You can also edit the posting date and time, the current date and time are set when you create the Delivery Note.

### Statuses

These are the statuses a Delivery Note can be in:

- **Draft**: A draft is saved but yet to be submitted to the system.
- **To Bill**: Yet to be billed using a Sales Invoice.
- **Completed**: Submitted and sent all the Items.
- **Return Issued**: All the Items have been returned.
- **Cancelled**: Cancelled the Delivery Note.
- **Closed**: The purpose of the Close is to manage short-closing. For example, your Customer ordered for 20 qty but closed at 15 qty. The remaining 5 is not to be sent or billed.

### Partial Deliveries

When you create a Delivery Note from a Sales Order, the quantities can be changed. So if the Sales Order contains 10 Items to be delivered and you're delivering only 5 this week and the remaining next week, then you can create 2 Delivery Notes in two weeks.

### From Pick List

You can create Delivery Notes in bulk, from Pick Lists also. From a submitted Pick List, click on Create -> Delivery Note.

This would create separate Delivery Notes for Sales Orders, grouped by Customer.
If a Pick List Item is not linked to a Sales Order(added manually by user), a separate DN would be created for all those items as well.

## Related Actions

### Customer Purchase Order Details

You can enter the Customer's Purchase Order number here for Reference.

### Address and Contact

- **Shipping Address**: The Customer's address where the Items will be shipped.
- **Contact Person**: If the Customer is an organization, add the Contact person in this field.

For India, the following details can be added for GST:

- Customer GSTIN
- Place of Supply
- Billing Address GSTIN
- Company GSTIN
- Company Address Name

Contacts and Addresses are stored separately so that you can attach multiple Contacts or Addresses to the customer.

### Currency and Price List

You can set the currency in which the Deliver Note is to be sent. This is usually fetched if set in the Sales Order. If you set a Pricing List, then the item prices will be fetched from that list. Ticking on Ignore Pricing Rule will ignore the Pricing Rules set in Accounts > Pricing Rule.

### Warehouses

- **Set Source Warehouse**: This is where the Items will be sourced from to send to the Customer.
- **To Warehouse**: In a regular Sales scenario, the Item exits your Warehouse and reaches the Customer. However, if you wish to retain sample stock, enter a Warehouse here.

### Items Table

- **Barcode**: You can track Items using barcodes.
- The Item Code, name, description, Image, and Manufacturer will be fetched from the Item master.
- **Scan Barcode**: You can add Items in the Items table by scanning their barcodes if you have a barcode scanner.
- **Discount and Margin**: You can apply a discount on individual Items percentage-wise or the total amount of the Item.
- **Rate**: The Rate is fetched if set in the Price List and the total Amount is calculated.
- **Item Tax Template**: You can set an Item Tax Template to apply a specific Tax amount to this particular Item.
- The Item Weight details per unit and Weight UOM are fetched if set in the Item master.
- **Warehouse and Reference**: The Warehouse from which the Items are sent to the Customer is shown. Also, a Sales Order will be shown if this Delivery Note was the creation flow: 'Sales Order > Deliver Note'.
- **Batch No and Serial No**: If your Item is serialized or batched, you will have to enter Serial Number and Batch in the Items table. You are allowed to enter multiple Serial Numbers in one row (each on a separate line) and you must enter the same number of Serial Numbers as the quantity.

The 'Available Qty at From Warehouse', 'Available Batch Qty at From Warehouse', and 'Installed Qty' will be shown.

**Note**: The Item has to be serialized or batched for these features to work. If the Item is serialized a popup will appear where you can enter the Serial Numbers.

- Expense Account is the account from which the amount will be debited. Ticking on 'Allow Zero Valuation Rate' will allow submitting the Delivery Note even if the Valuation Rate of the Item is 0. This can be a sample item or due to a mutual understanding with your Supplier.
- Accounting Dimensions help to tag each transaction with different Dimensions without the need for creating new Cost Centers.
- **Page Break** will create a page break just before this Item when printing.

### Tracking Quality Inspection

If for certain Items, it is mandatory to record Quality Inspections (if you have set it in your Item master), you will need to update the "Quality Inspection" field. The system will only allow you to "Submit" the Delivery Note if you update the "Quality Inspection".

After enabling Inspection Criteria in the Item form for Sales and attaching a Quality Inspection Template there, Quality Inspections can be recorded in Delivery Notes.

### Taxes and Charges

The Taxes and Charges will be fetched from the Sales Order.

The total taxes and charges will be displayed below the table.

To add taxes automatically via a Tax Category, visit this page.

Make sure to mark all your taxes in the Taxes and Charges table correctly for an accurate valuation.

#### Shipping Rule

A Shipping Rule helps set the cost of shipping an Item. The cost will usually increase with the distance of shipping.

### Additional Discount

Any additional discounts to the whole order can be set in this section. This discount could be based on the Grand Total i.e., post tax/charges or Net total i.e., pre tax/charges. The additional discount can be applied as a percentage or an amount.

### Terms and Conditions

In Sales/Purchase transactions there might be certain Terms and Conditions based on which the Supplier provides goods or services to the Customer. You can apply the Terms and Conditions to transactions and they will appear when printing the document.

### Transporter Information

If you outsource transporting Items to their delivery location, the transporter details can be added. This is not the same as drop shipping.

- **Transporter**: The Supplier who will transport the Item to your Customer. The transporter feature should be enabled in the Supplier master to select the Supplier here.
- **Driver**: You can add a Driver here who will drive the mode of transport.

The following details can be recorded:

- Distance in km
- Mode of Transport whether road, air, rail, or ship.

For India, GST:

- GST Transporter ID
- Transport Receipt No
- Vehicle No

The Transport Receipt Date and Driver Name will be fetched.

### More Information

The Delivery Note can be linked to the following for tracking purposes:

- Project
- Campaign
- Source

### Printing Settings

#### Letterhead

You can print your Delivery Note on your company's letterhead.

'Group same items' will group the same items added multiple times in the Items table. This can be seen when your print.

#### Print Headings

Purchase Receipt headings can also be changed when printing the document. You can do this by selecting a **Print Heading**. To create new Print Headings go to: Home > Settings > Printing > Print Heading.

There are additional checkboxes for printing the Delivery Note without the amount, this might be useful when the Item is of high value. You can also group the same Items in one row when printing.

### Status

The status of the document and installation percentage is shown here. Any additional instructions for delivery can be entered here.

### Commission

If the sale took place via one of your Sales Partners, you can add their commission details here. This is usually fetched from the Sales Order.

### Sales Team

**Sales Persons:** ERPNext allows you to add multiple Sales Persons who may have worked on this deal.

This is usually fetched from a Sales Order.

### Shipping Packets or Items with Product Bundle

If you are shipping Items that have a Product Bundle, ERPNext will automatically create a "Packing List" table for you based on the sub-Items in that Item.

If your Items are serialized, then for Product Bundle type of Items, you will have to update the Serial Number in the "Packing List" table.

### Packing Items into Cases, for Container Shipment

If you are doing making the delivery via container shipment or by weight, then you can use the Packing Slip to break up your Delivery Note into smaller units.

You can create multiple Packing Slips for your Delivery Note and ERPNext will ensure that the quantities in the Packing Slip do not exceed the quantities in the Delivery Note. Note that you can create a Packing Slip from a Delivery Note only when the Delivery Note is in the Draft stage.

### After Submitting

When the Delivery Note is submitted, a Stock Ledger Entry is made for each Item and stock is updated. Pending Quantity in the Sales Order is updated (if applicable).

The Dashboard will show the following options:

- Installation Note
- Sales Return
- Delivery Trip
- Sales Invoice

> Tip: To disallow the creation of Delivery Notes without a Sales Order against it:

### Returning a Sales Order

Once you've delivered a Sales Order using a Delivery Note, you can create a return entry in case the Customer returns the Item.

### Skipping Delivery Note

If you don't want to create a Delivery Note after a Sales Order and directly want to create a Sales Invoice, enable the feature for it in Selling Settings.

### Related Topics

1. Warehouse
2. Delivery Note Stock Error
3. Material Transfer From Delivery Note and Purchase Receipt
4. Installation Note
5. Delivery Trip
