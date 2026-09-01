---
title: "Web Forms"
source_url: "https://docs.frappe.io/erpnext/web-form"
section: website
---

# Web Forms

## Overview

ERPNext provides Web Forms to enable external stakeholders—such as customers, suppliers, job applicants, students, and guardians—to interact with your system. According to the documentation, "Web forms are similar to the forms you generally fill in various websites on the internet."

The platform distinguishes between two interfaces: the Desk View for regular organizational users and the Web View for occasional users. Web Forms are part of the Web View interface.

## Creating a Web Form

To create a new Web Form, navigate to **Home > Website > Web Site > Web Form**. You'll select a DocType as the foundation, and the system automatically generates a Route based on your form's title. You can add introductory text and select fields from your chosen DocType.

## Configuration Options

Web Forms offer ten key checkboxes to control functionality:

1. **Published** — Required to make the form accessible
2. **Login Required** — Restricts access to authenticated users
3. **Route to Success Link** — Redirects users after submission
4. **Allow Edit** — Permits editing after initial save
5. **Allow Multiple** — Enables creating multiple records per user
6. **Show as Grid** — Displays records in table format
7. **Allow Delete** — Permits record deletion
8. **Allow Comments** — Enables user comments
9. **Allow Print** — Allows printing in selected formats
10. **Allow Incomplete Forms** — Permits partial submissions

## Features

**Sidebar Settings** provide contextual links alongside your form. **Child Tables** integrate nested data structures similar to standard forms. **Payment Gateway Integration** allows requesting payments, useful for ticketing scenarios.

**Portal Users** feature role-based access control while restricting Desk View access. **Custom Scripts** enable input validation and custom behaviors. **Custom CSS** allows styling customization.

**Success Messages** display after form submission, with optional redirect URLs for unauthenticated users.

Submitted data automatically stores in the associated DocType document.
