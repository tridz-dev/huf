---
title: "Easy steps to setup Workflow"
source_url: "https://docs.frappe.io/erpnext/easy-steps-to-setup-workflow"
section: configurations
---

# Easy steps to setup Workflow

When a company has multiple levels of approval for a document, a Workflow can be set. In ERPNext, you can go to Workflow list --> Create New --> Name the workflow and define:

1. States
2. Transition rules.

## States

When a document is passed on for different levels of approval, there are states defined at each level for the role of the user.

![](/files/Y3TzzU2.png)

## Transition Rules

For instance: A **Sales user** is only allowed to create a **Quotation** and it can be saved in the **Draft** state. Further, it can be sent to the **Sales Manager** for approval and the User with this role can have the permission to either **Approve** or **Reject** the Quotation after which it can either be sent to the **Draft** State if **Rejected** or final **Approved** State.

![](/files/xJUtkGy.png)

## Error Messages

**A document cannot be Cancelled before it is Submitted.**

[This is a typical error faced by users who define the state of the Document cancelled before Submitting it. Doc Status 1 defines that the Document will be Submitted at that State, thus the State with Doc status 2 should only be defined in the Transition after the State with Doc status 1. ]

Setup a Simple Workflow to begin with and let us know what you think more on Workflows! We love to see our Users Happy!! ;)
