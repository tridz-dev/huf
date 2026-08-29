---
title: "Request for Quotation"
source_url: "https://docs.frappe.io/erpnext/request-for-quotation"
section: buying
---

# Request for Quotation

**A Request for Quotation is a document that an organization sends to one or more suppliers asking a quotation for items.**

![Buying Flow](/files/buying_flow_rfq.png)

To access **Request for Quotation**, open the "Buying" workspace and, under "Reports & Masters" > "Buying", click on "Request for Quotation".

## 1. Prerequisites

Before creating and using a **Request for Quotation**, it is advised that you create the following first:

* [Supplier](/erpnext/supplier)
* [Item](/erpnext/item)

## 2. How to create a Request For Quotation

1. Go to the **Request For Quotation** list and click on "+ Add Request for Quotation".
2. Enter the *Required Date*, by which you'll need the requested materials.
3. Fill the "Suppliers" list with possible suppliers.
If you set a *Contact* and *Email Id*, that can later be used for sending the **Request For Quotation** via email and grant access to the supplier portal.
4. In the next table, enter the required items along with UOM and quantity, as well as the target warehouse.
5. The *Warehouse* can be left blank if *Maintain Stock* is not enabled for the item.
6. If you want to send the **Request for Quotation** to your suppliers as an email, you can create an **Email Template** and select it here. In the template, you can use special variables for supplier specific data:
  - `{{ update_password_link }}`: A link where your supplier can set a new password to log into your portal.
  - `{{ portal_link }}`: A link to this RFQ in your supplier portal.
  - `{{ supplier_name }}`: The company name of your supplier.
  - `{{ contact.salutation }} {{ contact.last_name }}`: The contact person of your supplier.
  - `{{ user_fullname }}`: Your full name.

  Apart from these, you can access all values in this RFQ, like `{{ message_for_supplier }}` or `{{ terms }}`.

7. You can check how the email will look for a specific supplier by using the "Preview Email" button.

![Preview Email](/files/email-preview.png)

8. If you want to send further attachments to your suppliers, you can enable the checkbox *Send Attached Files*. This will add each file attached to the **Request for Quotation** as an attachment to each supplier email.
9. Once you're done, save the **Request for Quotation** as a draft.
10. When you're ready, you can submit the **Request for Quotation**. This will trigger an email to each supplier that has *Send Email* enabled.

![Create RFQ](/files/rfq-create.png)

A Request for Quotation (RFQ) can also be created from a submitted Material Request. Once an RFQ is created, you can print and send suppliers the PDF which will have all the details you entered relevant to the RFQ. You can also get their reply (Supplier Quotation) in ERPNext itself, see section [4.1 Supplier Quotation by User](#41-supplier-quotation-by-user). However, for a large number of items, your supplier may be more comfortable with an Excel sheet, etc.

## 3. Features

### 3.1 Get items from

The items in the items table can be fetched from other documents. The options are: Material Request, Opportunity, and Possible Supplier.

* **Material Request**: Items will be fetched from a submitted Material Request that you select. A Material Request can be searched with some matching words and a date range can also be selected to filter the Material Requests.
* **Opportunity**: Items will be fetched from a saved Opportunity. A date range can be selected here also.
* **Possible Supplier**: Select a possible supplier. Then if you have any submitted Material Requests against this supplier, items can be fetched from that.

![RFQ get items](/files/rfq-get-items.png)

### 3.2 Get Suppliers

Instead of entering the suppliers manually in the table, you can also fetch them using the 'Get Suppliers' button. When you click on **Tools > Get Suppliers**, you will see the field 'Get Suppliers By'. There are two options to fetch suppliers: By Tag or By Group.

* **By tag**: Go to 'Tag Category' via searching from the search bar. You must have created tags here first and assigned them to a Supplier in the Buying module. Then you can select 'By Tag'. On clicking Add 'All Suppliers', suppliers with matching tags will be fetched.
* **By Group**: Select 'Supplier Group' and choose the supplier group from which suppliers need to be added. For example, if you select Hardware, all your hardware suppliers will be added so that you can get a quote from all of them.

![RFQ get suppliers](/files/rfq-get-suppliers.png)

In the Supplier table, on expanding a row with the inverted triangle, you'll see an option 'Download PDF' which will open a PDF of the RFQ.

### 3.3 Link to Material Requests

When you click on **Tools > Link to Material Requests**, it links the Request for Quotation to available Material Requests. The items should be the same in the Request for Quotation and the Material Request.

![Link to Material Request](/files/link-to-material-request.png)

Now, when the Request for Quotation is saved, you can see in the Dashboard that it is linked to the Material Request. If there are multiple Material Requests with the same items, then the link will be created with the newest Material Request.

### 3.5 Terms and Conditions

In Sales/Purchase transactions, there might be certain Terms and Conditions based on which the Supplier provides goods or services to the Customer. You can apply the Terms and Conditions to transactions and they will appear when printing the document. To know about Terms and Conditions, [click here](/erpnext/terms-and-conditions)

### 3.6 Print Settings

#### Letterhead

You can print your request for quotation/purchase order on your company's letterhead. Know more [here](/erpnext/letter-head).

'Group same items' will group the same items added multiple times in the items table. This can be seen when you print it.

#### Print Headings

Titles of your documents can be changed. Know more [here](/erpnext/print-headings).

#### Special properties

When printing a RFQ via the "Tools > Download PDF" button, you are asked select the specific supplier you want to address. In the **Print Format** for RFQ, this information can be accessed via special properties:

* `{{ doc.vendor }}` holds the selected supplier ID.
* `{{ doc.items[i].supplier_part_no }}` holds the *Supplier Part Number* of a requested line item.

The data of the first supplier will be used while rendering the standard print preview. If you want to print for a different supplier, please use the "Tools > Download PDF" button.

## 4. Creating a Supplier Quotation after RFQ

After creation of Request for Quotation, there are two ways to generate Supplier Quotation from Request for Quotation.

### 4.1 Supplier Quotation by User

1. Open Request for Quotation and click on **Supplier Quotation > Create**.

![Supplier Quotation from RFQ](/files/make-supplier-quotation-from-rfq.png)

2. Select the Supplier, click on the supplier again. In this page, click on the + next to 'Supplier Quotation'. A new Supplier Quotation page will be opened, user has to enter the quantity, rate and submit it.

![Supplier Quotation from Supplier](/files/supplier-quotation-from-sup.png)

### 4.2 Supplier Quotation from Supplier

1. If a [Contact](/erpnext/contact) is created for the Supplier and an email address is associated with the Contact, the Contact details and the email address will be fetched on selecting the Supplier. Create a Contact and email address if not present already.
2. Click on **Tools > Send Emails to Suppliers**.

**If the Supplier's account is not present**: The system will create the Supplier's account and send details to the Supplier. The Supplier will need to click on the link (Password Update) present in the email. After the password update, the Supplier can access their portal with the 'Request for Quotation' form. The Supplier will be created as a Website User.

![Supplier email if account not present](/files/supplier-email-with-update-password.png)

**If Supplier's account is present**: The system will send a Request for Quotation link to the Supplier. The Supplier must log in using his credentials to view the Request for Quotation form on the portal.

![Supplier email if account present](/files/supplier-email-normal.png)

3. Either way, when the Supplier logs in, the following screen will be shown to them. From here they can send you a quotation:

![Supplier Quotation Screen](/files/rfq-supplier-quotation.png)

The Supplier has to enter the amount and notes (payment terms) on the form and click on Submit. In the Quotations section, previous quotations will be visible.

4. On submission, ERPNext will create a Supplier Quotation (draft mode) against the Supplier. The user has to review the Supplier Quotation and submit it. When all the items from the Request for Quotation have been quoted by a Supplier, the quote status is updated to 'Received' in the 'Suppliers' table of the Request for Quotation.

![RFQ status after supplier quote](/files/rfq-supplier-quoted.png)

Read [Supplier Quotation](/erpnext/supplier-quotation) to know more.

## 5. Video

## 6. Related Topics

1. [Purchase Order](/erpnext/purchase-order)
2. [Supplier](/erpnext/supplier)
3. [Supplier Quotation](/erpnext/supplier-quotation)
4. [Quotation](/erpnext/quotation)
5. [Material Request](/erpnext/material-request)
