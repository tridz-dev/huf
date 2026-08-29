---
title: "Workflows"
source_url: "https://docs.frappe.io/erpnext/workflows"
section: configurations
---

# Workflows

**With workflows you can rewrite how a particular process/workflow is approved in ERPNext.**

You can set multiple levels of approval for an ERPNext Workflow. To allow multiple people to submit multiple requests, for approvals by multiple users, ERPNext requires you to fill the Workflow conditions. ERPNext tracks the multiple permissions before submission.

Consider a scenario, where multiple levels of approval are required for a quotation. A sales person (user with 'Sales User' role) will create a quotation. Then it is either approved or rejected by a sales lead (user with 'Sales Manager' role). If approved by sales lead, it is further approved or rejected by regional manager (user with 'Regional Manager' role).

To make a Workflow and transition rules go to:

> Home > Settings > Workflow

Once a Workflow is created, you can take actions on it via [Workflow Actions](/erpnext/workflow-actions).

## 1. Prerequisites

Before creating a Workflow, it is advised to create these first:

* [Workflow Actions](/erpnext/workflow-actions)
* Workflow States like Approved, Canceled, etc.

## 2. How to Create a Workflow

1. Go to the Workflow list, click on New.
2. Enter a name for the **Workflow** and select the DocType on which to be applied.
3. Enter the different states of the Workflow. Enter Doc Status for them, select which field to update from the Update Field column, enter what the value will be updated to under Update Value.

The Workflow States can have different colors according to the state. Eg: Green for success. Document statuses: Saved = 0, Submitted = 1, Cancelled = 2.

![Workflow](/files/workflow.png)

4. Enter the Transition Rules.

![Workflow Transition Rules](/files/workflow-transition-rules.png)

### 2.2 Things to note when creating a Workflow

* Creating a Workflow in ERPNext essentially overrides the regular Save and Submit workflow. Thus the document will function based on your Workflow and not based on the pre-set code workflow. Hence there might be no Submit button/option if you have not specified it in the Workflow you create.

If you don't apply a Workflow to a document, and that document is submittable, then it has the default workflow with states: Draft - Submitted - Cancelled. If you are applying a Workflow to a submittable document, then those default states should be handled by the user.

* A document cannot be canceled unless it is submitted.
* If you wish to give the option to cancel, you will have to write a workflow transition step that says from submitted you can cancel.
* If fields under Update Field column are not updated, a new custom field will be created with the name you set in the 'Workflow State Field' field.

### 2.3 Other options for a Workflow

1. Is Active: On ticking this, all other Workflows for the selected DocType become inactive.
2. Don't Override Status: This Workflow's status will not override the status of the document (Quotation) in the list view.
3. Send Email Alerts: Emails will be sent to the user with next possible workflow actions.

## 3. Features

### 3.1 Enable/Disable Optional Workflow State

> Introduced in Version 12

In States, optional Workflow state means that the state may not be a part of final approval.

E.g. states like Canceled or Rejected can be optional. ![Optional State](/files/workflow-optional-state.png)

**Note:** Workflow Actions are not created for optional states.

### 3.2 Conditions

You can also add a condition for the Transition to be applicable. For example, in this case, if sales executive creates a quotation with grand total of $100,000 or more, a particular role must approve. For this to happen in the particular transition, you can set a property for **Condition**:

```
doc.grand_total <= 100000
```

Here, `grand_total` is the field name of the field 'Grand Total' of Quotation. To see the field name of a field go to Menu > Customize.

This can be extended to any property of the document.

> Introduced in Version 13

In Version 13, you can use date/time, session, get_value and get_list functions in your condition expressions.

Allowed functions:

* frappe.db.get_value
* frappe.db.get_list
* frappe.session
* frappe.utils.now_datetime
* frappe.utils.get_datetime
* frappe.utils.add_to_date
* frappe.utils.now

Examples:

```
doc.creation > frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-5, as_string=True, as_datetime=True)
```

## 4. Example of a Quotation Approval Process

When a quotation is saved by sales user, the status of the document changes to "Draft" and when clicked on submit the status changes to 'Approval Pending By Sales Manager':

![Workflow State in Transaction](/files/workflow-status-in-transaction.png)

When the Sales Manager logs in, he can either Approve or Reject. If approved the status of the document changes to "Approval Pending By Regional Manager".

![Workflow Action Options](/files/workflow-action-options.png)

When the Regional Manager opens the quotation, he can finally "Approve" or "Reject" it.

![Workflow Action Options](/files/workflow-action-options-2.png)

## 5. Video

## 6. Related Topics

1. [Workflow Actions](/erpnext/workflow-actions)
2. [Assignment Rule](/erpnext/assignment-rule)
