---
title: "DocType"
source_url: "https://docs.frappe.io/erpnext/doctype"
section: data-model
---

# DocType

**A DocType represents the fundamental foundation of applications built on the Frappe Framework.**

According to the documentation, it "describes the Model and the View of your data" and specifies what fields are stored and how they interact. DocTypes enable the creation of custom forms within ERPNext, such as Sales Orders and Work Invoices.

## Creating a New DocType

To add a new DocType, navigate to Setup > Customize > DocType > New, then:

1. Enter the DocType name
2. Select the target module
3. Save the configuration

## Key Configuration Sections

**Fields**: Add custom data fields with specified types, labels, and mandatory requirements.

**Naming**: Configure automatic naming patterns using fields, naming series, or custom formats, with options for title case or uppercase styling.

**Form Settings**: Manage image fields, attachments, timelines, and other display elements.

**View Settings**: Define search fields, default sorting, and display preferences.

**Permission Rules**: Control user access and modification capabilities.

**Web View**: Enable public access for website users.

## Advanced Properties

- **Is Submittable**: Allow forms to be submitted rather than just saved
- **Is Child Table**: Create dependent table structures within parent DocTypes
- **Is Single**: Restrict to one form instance
- **Is Tree**: Enable hierarchical parent-child relationships
- **Quick Entry**: Enable rapid data entry with minimal required fields
- **Track Changes/Seen/Views**: Maintain audit logs of document modifications and user interactions
- **Custom?**: Automatically marked for custom DocTypes
