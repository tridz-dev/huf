---
title: "Document Naming Settings"
source_url: "https://docs.frappe.io/erpnext/document-naming-settings"
section: data-model
---

# Document Naming Settings

Masters and transactions can be assigned prefixes through naming series in ERPNext. The system allows you to establish multiple series for documents, each with its own prefix pattern (for example, INV12#### generates INV120001, INV120002, etc.).

## Setting up Naming Series for Documents

To configure naming series:

1. Select the transaction type requiring a series; the system displays current series in a text box
2. Edit the series with unique prefixes, placing each on a new line (the first becomes the default)
3. Optionally check "User must always select" to require explicit series selection
4. Use the "Update Series" section to modify starting points
5. Click Update to apply changes

> Note: Access this via Home > Settings > Document Naming Settings. After adding new series, navigate to Settings > Reload to view them.

## Financial Year in Naming Series

Including financial year information requires entering patterns like "ACC-SINV-.19-20.-" where the fiscal year appears. Using 'YYYY' automatically inserts the current year. Separate series per financial year represents common practice.

## Updating Current Values for Existing Series

To change a series' sequence number:

1. Select the prefix in the Update Series section
2. The system retrieves and displays the current value
3. Modify the sequence number as needed
4. Click Update Series Number

For instance, resetting a Sales Order series from 16 to 50 means subsequent orders begin at the new number.

## Using Field Values in Naming Series

Custom field values enable quick identification. Example: A "Vendor ID" custom field on Supplier documents could create naming patterns like "PO-1503-WN-00001" using the format "PO-.YY.MM.-.vendorid.-.####"

## Updating Amended Documents

Configure amended document naming by navigating to the Amended Documents section and selecting either a default counter for all doctypes or customized naming for specific ones. Click "Update Amendment Counter" to save.

## Related Topics

- [Bulk Rename](/erpnext/bulk-rename)
