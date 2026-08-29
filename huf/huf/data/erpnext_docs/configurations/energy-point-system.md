---
title: "Energy Point System"
source_url: "https://docs.frappe.io/erpnext/energy-point-system"
section: configurations
---

# Energy Point System

**Energy Points System is a gamification of user engagement to recognize and incentivize users for their contributions and activities within ERPNext.**

This system can be used to track the performance of each user.

> To enable Energy Point System go to
>
> **Energy Point Settings** > **Enabled**

## How to use the Energy Point System?

To start using this system you need to create some Energy Point Rules (see section 3. How to create Energy Point Rules?) so that users can get energy points based on their activities.

## What are Energy Point Rules?

Energy Point Rules store the information about the activity and the value of points to be allocated.

Energy Point Rule has the following fields:

| Field | Description |
|-------|-------------|
| Reference DocType | Document Type you want to apply the rule on eg. Task, ToDo, Issue, etc. |
| For Document Event | Options: Save, Submit, Cancel, and Custom.**Note:** If "Custom" option is selected then the "Conditions" field becomes mandatory |
| Points | Points to be allocated. |
| Allot Points To Assigned Users | If checked, users assigned to the reference document will get respective points. eg. If users Santosh and Albert are assigned to a particular task then both of them will get points when the document fulfills the condition |
| User Field | Field from which user will be selected eg. `Resolved By`, `Modified By`, `Owner`, etc. can be used. If `Modified By` is selected, the last person to satisfy the doc condition will get the points. |
| Multiplier Field | Field which stores value for the multiplier. This field can take numeric and decimal values which will be multiplied with points defined in the rule. For example: 2 (multiplier) * 10 (points set in the rule) = 20 points |
| Condition | Condition for the point allocation. eg. `doc.status == 'Closed'`The above condition will check whether the `status` field in the document is 'Closed' and if yes then the points will be allocated to the user. |
| Apply Only Once | The rule will be applied only once per document. |

## How to create Energy Point Rules?

Search for **Energy Point Rule** > create new Energy Point Rule

Take a look at the following example rule:

![](/files/image13b0d0.png)

The screenshot above is the rule for **Issue Closing**. So when any user closes the issue he/she will be rewarded with **10** points.

Other cases can be covered similarly.

Suppose, you want to create a rule where a user gets points on completing a task, you can do so by creating following rule

![](/files/image1d19dd.png)

## Features

### 4.1 Auto Point allocation

Based on energy point rules created, users will automatically get points when they complete activities which are tracked using the Energy Point System.

### 4.2 Review System

Review system can be used to "Appreciate" or "Criticize" someone's work, check out the following GIF for the review process.

![](/files/review-system.gif)

For reviewing, the user needs to have review points which can be assigned by System Manager through **Energy Point Settings**.

You can also setup auto review point allocation from 'Energy Point Settings':

![](/files/imaged9995e.png)

### 4.3 Leaderboard

> Go to Social Home > Leaderboard (side navigation bar)

The leaderboard shows the user's standing in the organization.

![](/files/leaderboard.png)

## Related Topics

1. [Milestone Tracking](/erpnext/milestone-tracker)
