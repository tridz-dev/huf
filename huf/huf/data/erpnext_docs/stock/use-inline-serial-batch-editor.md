---
title: "Use Inline Serial / Batch Editor"
source_url: "https://docs.frappe.io/erpnext/use-inline-serial-batch-editor"
section: stock
---

# Use Inline Serial / Batch Editor

The Inline Serial / Batch Editor enables you to add and manage Serial Numbers and Batches directly within item rows of stock documents. Rather than using a separate pop-up, entries appear in a table format right where you're working, and all changes save together.

## How to Enable It

1. Open **Stock Settings** (search for "Stock Settings" in the search bar).
2. Go to the **Serial & Batch Item** section.
3. Make sure **"Use Serial No / Batch Fields"** is unchecked.
4. Tick the checkbox **"Use Inline Serial / Batch Editor"**.
5. Click **Save**.

The feature is now active across your site. It's enabled by default on new installations.

> Tip: If you don't see the editor after enabling it, refresh your browser page once.

## Where You Will See It

Open any of these documents and click on an item row to expand it. The **Serial / Batch Entries** table appears inside for items with Serial Numbers or Batches:

- Purchase Receipt and Purchase Invoice (including Rejected quantity section)
- Sales Invoice, POS Invoice and Delivery Note (including bundled / packed items)
- Stock Entry
- Stock Reconciliation
- Subcontracting Receipt (items and supplied items)
- Pick List
- Asset Capitalization and Asset Repair

## Why Use It? (Benefits)

- **Everything in one place** — manage serial numbers or batches directly on the item row without switching contexts.
- **Faster** — changes batch-save in one operation rather than generating multiple server calls per entry.
- **Nothing saved by accident** — serial/batch modifications remain local until you save the document.
- **Handles large lists easily** — entries display in 10-row pages with simple navigation, accommodating hundreds of entries.
- **Missing serials and batches are created for you** — on incoming documents, the system automatically creates new serial numbers or batches that don't yet exist.

## How to Use It

### Adding entries

1. Click on the item row to expand it and locate the **Serial / Batch Entries** table.
2. Click **Add row**.
3. Select the Serial Number / Batch from the dropdown (or enter a new one) and input the quantity.
4. Repeat as needed, then **Save** the document.

The item's quantity and Total Qty automatically update as you add entries.

### Editing entries

- Click directly on a Serial No, Batch No or Qty cell and type the new value—like editing a spreadsheet.

### Deleting entries

- Tick the checkbox at the start of one or more rows, then click **Delete row**.
- To clear everything, tick the table header checkbox (select all) and click **Delete All**. Removing all entries and saving removes the linked Serial and Batch Bundle.

### The (three dots) menu

Additional tools appear at the bottom right:

- **Auto Fetch Serial Nos / Batch Nos** *(outgoing documents like Delivery Note)* — specify quantity and the system selects entries based on the **Pick Serial / Batch Based On** rule (FIFO, LIFO or Expiry). Replaces current table contents, skips reserved stock, and saves automatically.
- **Scan Serial Nos / Scan Batch Nos** — use a barcode scanner (or type and press Enter) to add entries individually. Scanning the same batch again increases its quantity.
- **Create Serial Nos from Range** *(serial items)* — type a range like `SN-01::10` to add SN-01 through SN-10 in one step.
- **Download** — export current entries or a blank template as CSV.
- **Upload** — complete the CSV template and upload to load many entries at once. Missing serial numbers and batches are created automatically on incoming documents.

### Moving between pages

With more than 10 entries, use the arrow buttons at the table's bottom to navigate pages or type a page number directly. The outer arrow buttons jump to the first or last page.

## Good to Know

- The editor appears only while the document is in **Draft**. Entries lock after submission.
- If an item row has **"Use Serial No / Batch Fields"** enabled, that row retains simple text fields and the inline table remains hidden.
- Prefer the previous pop-up dialog? Untick **"Use Inline Serial / Batch Editor"** in Stock Settings to restore earlier behavior.
