---
title: "Email Dropbox"
source_url: "https://docs.frappe.io/erpnext/email-dropbox"
section: configurations
---

# Email Dropbox

When you receive emails from Leads, Customers, Suppliers, or other business partners, you might wish to attach those to their relevant records in ERPNext. One way to do so is to save the email and upload it as an attachment. However, this could turn into a cumbersome process. ERPNext offers a better way to handle this through its "Email Dropbox" feature.

When enabled, each record in ERPNext will have it's own unique email address to which you can forward emails. You can click on the email address to copy it to your clipboard, which can then be added to the "To", "Cc", or "Bcc" field of the email that you wish to send.

## 1. Enable Email Dropbox Feature

In [Email Account](/erpnext/email-account), check 'Enable Email Dropbox'.

![Enable Email Dropbox](/files/enable_email_dropbox.png)

## 2. Copy Unique Email Address in Any Record

Once the Email Dropbox feature is enabled, the unique email address becomes visible in all the records. You can click on the same and the address is copied to your clipboard. You can directly paste it in 'To', 'Cc' or 'Bcc' and send the email.

![Unique Email Address](/files/unique_email_address_dropbox.png)

## 3. Email in Timeline

Once the email is received, ERPNext attaches it to the appropriate record and it will be visible in that record's timeline.

![Email in Timeline](/files/email_in_timeline.png)

### Related Topics

1. [Email Domain](/erpnext/email-domain)
2. [Email Account](/erpnext/email-account)
3. [Email Inbox](/erpnext/email-inbox)
