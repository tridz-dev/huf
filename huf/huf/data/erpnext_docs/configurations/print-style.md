---
title: "Print Style"
source_url: "https://docs.frappe.io/erpnext/print-style"
section: configurations
---

# Print Style

**Print Style** enables the creation of custom CSS styles that can be applied to Print Formats in ERPNext.

ERPNext includes four preset styles: Monochrome, Modern, Redesign, and Classic. Users have the ability to develop additional styles using CSS for application across all print formats.

## How to create a new Print Style?

1. Navigate to Home > Settings > Print Style and select New
2. Provide a name for the Print Style
3. Input the CSS code that will determine the style's appearance
4. Save the configuration

Custom styles created this way work with both standard and custom print formats. To identify available CSS classes, open a standard print format in a new page and examine the source code.

A default Print Style can be configured through [Print Settings](/erpnext/print-settings).

All Print Format styles utilize "Bootstrap (Version 3) CSS Framework" as their foundation.

Developer mode users can enable a "Standard" option to generate a JSON file for the Print Style, which can be contributed as a default print style.

### Related Topics

1. [Print Format](/erpnext/print-format)
2. [Print Headings](/erpnext/print-headings)
3. [Letter Head](/erpnext/letter-head)
4. [Cheque Print Template](/erpnext/cheque-print-template)
