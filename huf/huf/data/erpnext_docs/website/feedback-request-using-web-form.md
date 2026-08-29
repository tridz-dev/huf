---
title: "Feedback Request Using a Web Form"
source_url: "https://docs.frappe.io/erpnext/feedback-request-using-web-form"
section: website
---

# Feedback Request Using a Web Form

In ERPNext version 11 and later, organizations can gather customer feedback through customizable tools. The process involves three main components:

## Feedback as a DocType

First, create a custom DocType that includes:
- A field listing DocTypes eligible for ratings
- A "Document Name" field configured as a "Dynamic Link" field
- A Rating field (or alternative data/select fields for feedback collection)

## Web Form for Feedback Form

After establishing the DocType, build a Web Form by importing standard fields from the Feedback doctype.

## Create a Notification

Set up a notification to distribute feedback request links to users. The notification can trigger based on standard conditions. The URL structure follows this pattern:

```
https://example.erpnext.com/feedback?new=1&document=Sales%20Order&document_name={{doc.name}}
```

Key URL components include:
- **example.erpnext.com** — Your ERPNext instance URL
- **feedback** — The custom doctype name
- **document=Sales%20Order** — The DocType receiving ratings
- **document_name={{doc.name}}** — Variable populating the specific document identifier in the feedback form

This approach enables collecting structured feedback directly from customers and users through an integrated web-based interface.
