---
title: "Customer, Contact and Address Relationship | ERPNext Documentation"
source_url: "https://docs.frappe.io/erpnext/customer-contact-and-address-relationship"
section: selling
---

# Customer, Contact and Address Relationship | ERPNext Documentation

A Customer, Contact, and Address represent interconnected but separate entities in ERPNext. As the documentation explains, "The Customer is the party you sell to, a Contact is a person you communicate with, and an Address is a location used for billing, shipping, or another purpose."

## Structure Overview

These three records work together in a hierarchy:
- **Customer** represents the commercial party
- **Contacts** are individual people associated with that customer
- **Addresses** are physical locations linked to the customer

The key advantage is that "one Customer can have several Contacts" and "one Customer can have several Addresses," allowing organizations to manage multiple employees and locations without duplicating customer records.

## Primary Record Selection

ERPNext uses primary flags to determine defaults:

- **Is Primary Contact** designates which person typically receives communications
- **Preferred Billing Address** indicates the standard invoicing location
- **Preferred Shipping Address** shows the typical delivery destination

However, users retain flexibility to override these defaults on individual transactions.

## Practical Example

For a customer like Summit Digital Stores, you might have:
- Morgan Lee as the primary contact (purchasing)
- Taylor Brooks as a secondary contact (accounts payable)
- Separate billing and shipping addresses

This structure prevents "creating a new Customer for every branch" and instead leverages linked records for organizational flexibility.

The documentation emphasizes that modifying primary designations affects future documents but "does not rewrite" details already stored on submitted transactions.
