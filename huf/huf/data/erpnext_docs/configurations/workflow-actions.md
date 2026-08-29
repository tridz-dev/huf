---
title: "Workflow Actions"
source_url: "https://docs.frappe.io/erpnext/workflow-actions"
section: configurations
---

# Workflow Actions

> Introduced in Version 11

**'Workflow Actions' is a single place where you can track and manage all pending actions you have to take on Workflows.**

Workflow Actions will send email notifications only if the 'Send Email Alert' checkbox is ticked in the Workflow that you've created.

To access Workflow Actions, go to:

> Home > Settings > Workflow Actions

If a User is eligible to take action on some workflows, emails will be sent to the user with the relevant document as attachment. From there the user can `Approve` or `Reject` the Workflow.

![Workflow Action Email](/files/workflow-actions-email.png)

Also the users will see entries in their Workflow Action list:

![Screenshot 2024-06-03 at 10.47.43 AM](/files/Screenshot 2024-06-03 at 10.47.43 AM.png)

**Note:**

* You can set email template for Workflow Actions on each state. The template might consist of a message for users to proceed with the next Workflow Actions.
* Workflow Actions will not be created for a transition to optional states.

### Related Topics

1. [Workflows](/erpnext/workflows)
2. [Assignment Rule](/erpnext/assignment-rule)
