---
title: "Sales Reports and Analytics"
source_url: "https://docs.frappe.io/erpnext/sales-analytics"
section: selling
---

ERPNext sales reports help teams review pipeline, orders, fulfilment, billing, customer activity, item performance, salesperson attribution, targets, and profitability. Choose a report based on the business question and confirm which transaction type, date field, and document status it uses.

## Before you begin

For reliable reports:

- Use consistent [Customers](/erpnext/customer), Territories, Sales Persons, Item Groups, and Warehouses.
- Submit operational transactions when the report measures confirmed activity.
- Assign the correct Company and posting or transaction dates.
- Keep Sales Team contribution and target allocations current.
- Use accurate buying or valuation rates for profitability reports.

## Open a sales report

1. Open the Selling workspace.
2. Select a report, or search for it by name.
3. Set Company, date range, and other filters.
4. Select **Refresh**.
5. Review, export, print, or chart the results as required.

## Choose the right report

| Question | Useful report |
|----------|---------------|
| Which orders are confirmed and still open? | Sales Order Analysis |
| What has been sold by Customer? | Sales Analytics or Customer-wise Sales |
| What has been sold by Item or Item Group? | Sales Analytics or Item-wise Sales |
| Which orders remain to be delivered or billed? | Sales Order Analysis and order status views |
| How much has each Sales Person contributed? | Sales Person-wise Transaction Summary |
| Are Sales Persons meeting targets? | Sales Person Target Variance |
| Are Territories meeting targets? | Territory Target Variance |
| Which invoices remain unpaid? | [Accounts Receivable](/erpnext/accounts-receivable) |
| Which sales are profitable? | Gross Profit |
| What is the CRM pipeline? | [Sales Pipeline](/erpnext/sales-pipeline) or CRM Analytics |

Report names and available filters can vary by ERPNext version and installed apps.

## Sales Analytics

Use Sales Analytics to compare sales across dimensions such as Customer, Customer Group, Territory, Item, Item Group, and Sales Person. Select the value or quantity basis and the period grouping needed for the comparison.

Use it for trends and concentration, not as a substitute for invoice-level audit.

## Sales Order reporting

[Sales Orders](/erpnext/sales-order) track confirmed demand, delivery progress, and billing progress. Review statuses and percentage fields to separate:

- To Deliver and Bill.
- To Deliver.
- To Bill.
- Completed.
- Closed.

Returns, cancellations, partial fulfilment, and short-closing can change outstanding values.

## Salesperson and target reporting

Salesperson reports depend on the Sales Team table. Confirm each transaction contains the correct [Sales Person contribution](/erpnext/sales-persons-in-the-sales-transactions).

Target variance also depends on [Sales Person Target Allocation](/erpnext/sales-person-target-allocation), Fiscal Year, Item Group, and Monthly Distribution.

## Gross Profit

Gross Profit compares sales value with buying or valuation information. Investigate:

- Missing or unusual buying rates.
- Returns and credit notes.
- Stock and non-stock Items.
- Currency conversion.
- Costing and valuation method.

Use the [General Ledger](/erpnext/general-ledger) and stock reports when accounting or inventory values need reconciliation.

## Export and saved views

Use report export for further analysis, but keep ERPNext as the source of the transactional record. Save commonly used filters or views where supported so teams compare the same scope.

## Troubleshooting

| Problem | What to check |
|---------|---------------|
| Report shows no data | Company, dates, transaction type, status, permissions, and dimension filters |
| Totals differ from another report | Confirm both reports use the same document type, date field, status, and return treatment |
| Sales Person totals are missing | Review Sales Team rows and contribution percentages |
| Target variance is empty | Review target rows, Fiscal Year, Item Group, Monthly Distribution, and submitted transactions |
| Gross profit is unexpected | Review valuation, buying rates, returns, and currency |

## Frequently asked questions

### Do draft transactions appear in sales reports?

It depends on the report. Reports of confirmed activity usually use submitted transactions, while pipeline-style reports may include drafts or opportunities.

### Why do two reports show different totals?

They may use different source DocTypes, statuses, dates, or grouping logic. Compare filters and report definitions.

### Can I add custom columns?

Use report customization or a custom Query or Script Report when standard output does not meet the requirement.

### Which report should I use for unpaid invoices?

Use Accounts Receivable rather than an order or sales analytics report.

## Related topics

- [Sales Order](/erpnext/sales-order)
- [Sales Invoice](/erpnext/sales-invoice)
- [Sales Person Target Allocation](/erpnext/sales-person-target-allocation)
- [Sales Pipeline](/erpnext/sales-pipeline)
- [CRM Analytics](/erpnext/crm-analytics)
