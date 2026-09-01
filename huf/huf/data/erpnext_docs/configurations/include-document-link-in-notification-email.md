---
title: "Include Document Link in Notification Email"
source_url: "https://docs.frappe.io/erpnext/include-document-link-in-notification-email"
section: configurations
---

# Include Document Link in Notification Email

While sending an email notification in ERPNext, many a times, we need the document ID to be a part of the email message as a link. For example, if we have set a reminder (notification) for every new Material Request, then we would want the link of the new Material Request to be also sent in email to us. To set that up, following the below steps:

1) Go to Notification list, click on New.
2) Create a new Notification for any DocType. In this case, we have taken an example of sending an Email Notification on creation of every new Material Request as shown below.

3) To send the document ID of the associated record as a link, copy the below snippet in the email message:

```
<a href="{{frappe.utils.get_url_to_form(doc.doctype, doc.name)}}">{{doc.name}}</a>
```

4) Now on creation of a new Material Request, following email will be received because of the above set Notification.

On clicking the link, you will be taken to the new Material Request.
