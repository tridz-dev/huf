---
title: "Deleting and Restoring Documents"
source_url: "https://docs.frappe.io/erpnext/restore-deleted-erpnext"
section: data-model
---

# Deleting and Restoring Documents

In ERPNext, you have the ability to remove documents that are no longer needed. This applies to master records such as Items and Customers, as well as transactional documents like Sales Orders and Payment Entries.

## Deleting Documents

To remove a document, access the dropdown menu within the document and choose the 'Delete' option.

For removing multiple cancelled records at once, you can select several items from the List View and delete them together in a single action.

> Note: "Any submittable document will not be deleted after submission. To delete a submitted document, you will be required to first 'cancel' the document."

## Restoration of Deleted Documents

If a document is removed unintentionally or becomes necessary after deletion, you can retrieve it from the Deleted Documents list.

Access this feature by navigating to:

> Home > Settings > Data > Deleted Documents

### How to Restore Deleted Documents

1. Navigate to the Deleted Documents List
2. Open the document you wish to restore
3. Select the **Restore** button

> Note: "If the document was deleted after getting canceled, it would be restored with a new name."

> Important: "Only those Users having System Manager Role assigned to them can restore deleted documents."
