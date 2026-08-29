---
title: "Field Types"
source_url: "https://docs.frappe.io/erpnext/field-types"
section: data-model
---

# Field Types

The following are the types of fields you can define while creating new ones, or while amending standard ones.

## Link

Link field is connected to another master from where it fetches data. For example, in the Quotation master, the Customer is a Link field.

## Dynamic Link

Dynamic Link field is one which can search and hold value of any document/doctype.

## Check

This will enable you to have a checkbox here.

## Select

Select will be a drop-down field. You can add multiple results in the Option field, separated by row.

## Table

A table will be a kind of Link field which renders another DocType within the current form. For example, the Item Table in the Sales Order is a Table field, which is linked to Sales Order Item DocType.

## Attach

Attach field allows you to browse a field from the File Manager and attach the same herein.

## Attach Image

Attach Image is a field wherein you will be allowed to attach Images of the format jpeg, png, etc. This becomes the Image representing that particular DocType.

## Text Editor

Text Editor is a text field. It has text-formatting options. In ERPNext, this field is generally used for defining Terms and Conditions.

## Date

This field will enable you to enter the Date in this field.

## Date and Time

This field will give you a date and time picker. The current date and time (as provided by your computer) are set by default.

## Barcode

In this field, you can specify the field as Barcode which will allow you to enter a Barcode number. Once you do that, the Barcode would automatically get generated against the number.

## Button

This kind of field will be an action button, like Save, Submit, etc.

## Code

If the Field Type is selected as code, you will be able to enter a Code to the field.

## Color

You will have the option of specifying the color for this Form.

## Column Break

Since ERPNext has multiple column layouts, using Column Breaks, you can divide a set of fields into a maximum of two columns.

## Currency

Currency field holds numeric value, like Item Price, Amount, etc. Currency field can have value up to six decimal places. Also, you can have a currency symbol being shown for the currency field.

## Data

The data field will be a simple text field. It allows you to enter a value of up to 140 characters, making this the most generic field type. To enable validations for Email, Name, or Phone Number inputs, set options to "Email", "Name", "Phone" in Settings > DocType.

## Float

Float field carries numeric value, up to nine decimal places. Precision for the float field is set via Set Precision.

> Setup > Settings > System Settings

The setting will be applicable on all the float field.

## Geolocation

Use Geolocation field to store GeoJSON feature_collection. Stores polygons, lines, and points. Internally it uses the following custom properties for identifying a circle.

## HTML

You can select the field to be an HTML field when you want the data to be entered in HTML format.

## Image

Image field will render an image file selected in another attach field.

For the Image field, under Option (in Doctype), a field name should be provided where the image file is attached. By referring to the value in that field, the image will be a reference in the Image field.

## Int (Integer)

The integer field holds numeric value, without decimal place.

## Small Text

Small Text field carries text content and has more character limit than the Data field.

## Long Text

You can define your field to a Long Text Field when you would want to enter data with an unlimited character limit.

## Text

This field type would allow you to add text in the field. The character limit in Small text, Long text and Text fields shall be determined based on the Relational Database Management System.

## Markdown Editor

This field will allow you to add the text in Markup language.

## Password

The password field will have decoded value in it.

## Percent

You can define the field as a Percentage field which in the background will be calculated as a percentage.

## Rating

You can define the field as a Rate field which in the background will be calculated as Rating.

## Read Only

Read Only field will carry data fetched from another form which will be non-editable. You should set Read Only as field type if its source for value is predetermined.

## Section Break

Section Break is used to divide the form into multiple sections.

## Signature

You can define the field to be a Signature field wherein you can add the Digital Signature in this field.

## Table MultiSelect

This is a combination of 'Link' type and 'Table' type fields. Instead of a child table with 'Add Row' button, in one field multiple values can be selected.

## Time

This is a Time field where you can define the Time in the field.

## Duration

You can use the Duration field if you want to define a timespan.

If you don't want to track duration in terms of days or seconds, you can enable "Hide Days" and "Hide Seconds" options respectively in your Form.
