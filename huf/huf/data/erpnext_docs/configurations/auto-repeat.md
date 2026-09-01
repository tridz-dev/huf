---
title: "Auto Repeat"
source_url: "https://docs.frappe.io/erpnext/auto-repeat"
section: configurations
---

# Auto Repeat

The Auto Repeat feature enables you to generate specific documents automatically at defined intervals. Beginning with version 12, any Form can be customized to support **repeatable** documents.

Consider this scenario: if you use a deferred expense system for certain items, you might need to create identical Journal Entries monthly to credit the Deferred Expense account and debit the Expense Account. You can manually create the initial Journal Entry, then establish an auto-repeat transaction for subsequent occurrences.

To access Auto Repeat, navigate to:
> Home > Settings > Automation > Auto Repeat

## 1. How to set up Auto Repeat

### 1.1 Customize the Form
1. Navigate to: **Home > Customization > Form Customization > Customize Form**.
2. Choose the form where you want to enable repeatable document creation.
3. Enable the 'Allow Auto Repeat' checkbox to permit repeatable documents for that Form. This step is essential for the document type to appear in the Reference Document field within the Auto Repeat doctype.

 ![Allow Auto Repeat](/files/allow-auto-repeat.png)

### 1.2 Set up Auto Repeat
1. Go to **Home > Settings > Automation > Auto Repeat > New**.
2. Choose the Reference Document Type (such as Journal Entry or Sales Invoice).
3. Select the Reference Document—the specific document you wish to repeat.
4. Specify the Start Date and optionally the End Date.
 When no End Date is set, documents will recur indefinitely until the Auto Repeat is disabled.
5. Choose the Frequency for generating repeatable documents (Daily, Weekly, Monthly, Quarterly, Half-yearly, Yearly).
6. Save.

### 1.3 Set up Auto Repeat directly from the document
Alternatively, you can activate Auto Repeat by selecting the **Repeat** option from the **Menu** in the Toolbar.

**Note**: The Repeat option becomes unavailable if a document is already configured for Auto Repeat.

![Repeat in Transactions](/files/repeat-option.png)

Selecting Repeat displays an Auto Repeat prompt. Complete the information and select Save.

![Auto Repeat Prompt](/files/auto-repeat-prompt.png)

## 2. Features

### 2.1 Submit on Creation

For submittable reference document types, an option called _Submit on Creation_ is available. When enabled, newly created documents are automatically submitted.

![Auto Repeat Submit on Creation](/files/submit-on-creation.png)

### 2.2 Notify by Email
To alert designated contacts when recurring documents are generated, enable 'Notify by Email' within the Notification section of Auto Repeat. This sends auto-generated documents to specified Email Addresses. The relevant fields are:

- **Recipients**: Email addresses receiving recurring document creation notifications.
- **Get Contacts**: This button retrieves contacts associated with the document set on Auto Repeat and populates the Recipients field.
- **Template**: Select an Email Template to auto-fill the Subject and Message fields.
- **Subject**: Email subject line (example: Recurring ToDo created successfully).
- **Message**: Email body content.
- **Preview Message**: This button displays a message preview.
- **Print Format**: Choose a print format determining how the document appears in the email.

> **Note**: For submittable documents set to Auto Repeat, verify that "Allow Print for Draft" is enabled in [Print Settings](/erpnext/print-settings) to receive the new recurring document in Auto Repeat Notification Email. Without this setting, you'll receive notification of document creation but not the document itself.

### 2.3 Repeat on a particular day
When frequency is set to Monthly, Quarterly, Half-yearly, or Yearly, recurring documents are created in those respective months on the same day as the Auto Repeat's 'Start Date'. To create recurring documents on alternative days, you can set:

- **Repeat on Day**: The day of the month for recurring document generation. For instance, with Monthly frequency and day 7 selected, documents generate on the 7th of each month.
- **Repeat on Last Day of the Month**: This option accommodates varying month lengths. In leap years, February's last day is the 29th; otherwise, it's the 28th. Enabling this creates recurring documents on the final day of respective months.

### 2.4 Ability to select weekdays for Auto Repeat

> Introduced in version 13

Weekly Auto Repeat frequency permits selecting specific days for recurring document creation.

![Auto Repeat Weekdays](/files/auto-repeat-weekdays.png)

### 2.5 Dashboard

The Auto Repeat document's Dashboard displays the recurring schedule. If no End Date is specified, the schedule shows only the Next Schedule Date.

![Auto Repeat Dashboard](/files/auto-repeat-dashboard.png)

### 2.6 Auto Repeat Frequency on the sidebar
When a document is configured for Auto Repeat, the frequency appears in the sidebar. You can click this status to access the linked Auto Repeat document.

![Auto Repeat Frequency](/files/auto-repeat-frequency.png)

### 2.7 Disable Auto Repeat
Checking this field halts the creation of recurring documents and disconnects the Auto Repeat document from the Reference Document.
