---
title: "Notification"
source_url: "https://docs.frappe.io/erpnext/notifications"
section: configurations
---

# Notification

You can configure various notifications in your system to remind you of important activities.

Examples of notifications include:
- Task completion dates
- Expected delivery dates for sales orders
- Expected payment dates
- Follow-up reminders
- Orders exceeding a particular value
- Contract expiry notifications
- Task completion or status changes

To access notification setup, navigate to: Home > Settings > Notification

## 1. Setting Up An Alert

To set up a notification:

1. Define events to watch under "Send Alert On":
   - **New**: Triggered when a new document of the selected type is created
   - **Save/Submit/Cancel**: Triggered when a document is saved, submitted, or canceled
   - **Days Before/Days After**: Triggers based on a reference date, useful for upcoming due dates or follow-ups
   - **Value Change**: Triggered when a particular field value changes
   - **Method**: Sends notification when a specific method is triggered (e.g., before_insert)
   - **Custom**: Sends notification to a selected email account

2. Select the document type to monitor (from Version 16, child document types are supported for "Days Before/Days After" events)
3. Set additional conditions if needed
4. Specify alert recipients (either a document field or fixed email addresses)
5. Compose the message
6. Save the notification

### 1.1 Setting a Subject

Retrieve field data using `doc.[field_name]` syntax wrapped in Jinja tags: "{{ doc.[field_name] }}". For example, "{{ doc.name }}" retrieves the document name. The resulting subject might display as "TASK#### has been created".

### 1.2 Setting Conditions

Use field conditions like "doc.status == 'Interested'" to control when notifications trigger. Combine multiple conditions using "and" or "or" operators. For instance, a task notification might use: "doc.status == 'Open' and doc.expected_end_date <= doc.creation".

### 1.3 Setting a Message

Both Jinja tags and HTML formatting are supported in messages. Templates can include conditional logic and access document fields:

```
<h3>Order Overdue</h3>

Transaction {{ doc.name }} has exceeded Due Date. Please take necessary action.

{% if comments %} Last comment: {{ comments[-1].comment }} by {{ comments[-1].by }} {% endif %}

<h4>Details</h4>

* Customer: {{ doc.customer }}
* Amount: {{ doc.total_amount }}
```

### 1.4 Setting a Value after the Alert is Set

To prevent duplicate notifications, define a custom property (via Customize Form) such as "Notification Sent". Use the "Set Property After Alert" field to update this property after sending. Reference this property in condition rules to ensure notifications aren't sent multiple times.

### 1.5 Example

Notification configuration includes defining criteria and setting recipients with messages.

## 2. Slack Notifications

Notifications can be directed to Slack channels by selecting "Slack" in channel options and providing a Slack Webhook URL.

### 2.1 Slack Webhook URL

To generate webhook URLs:

1. Visit https://api.slack.com/slack-apps
2. Click "Create a Slack App"
3. Name your app and select the appropriate workspace
4. Navigate to "Incoming Webhooks" and add a new webhook
5. Copy the webhook link and create a new Slack Webhook URL in ERPNext under Integrations > Slack Webhook URL
6. Select Slack and your channel in the notification configuration

### 2.2 Message Format

Slack doesn't support HTML formatting but allows markdown. Example:

```
*Order Overdue*

Transaction {{ doc.name }} has exceeded Due Date. Please take the necessary action.

{% if comments %}
Last comment: {{ comments[-1].comment }} by {{ comments[-1].by }}
{% endif %}

*Details*

• Customer: {{ doc.customer }}
• Amount: {{ doc.grand_total }}
```

## 3. System Notifications

System notifications appear in the notifications dropdown on the navigation bar. Version 12 introduced system notifications for assignments, mentions, shared documents, and energy points. Version 13 added system notifications as a dedicated alert channel.

System notifications display configured subjects and messages. Clicking a notification opens the Notification Log document, which includes attached files if "Attach Print" is enabled.

Both Email/Slack and system notifications can be enabled simultaneously by setting the main channel as Email or Slack and checking the system notification option.

## 4. WhatsApp

Version 13 introduced WhatsApp as an alert channel. Select "WhatsApp" in channel options and choose an appropriate Twilio number. WhatsApp messages require country codes.

### 4.1 Twilio Settings

Configure Twilio settings by obtaining credentials from your Twilio account. Only phone numbers activated in your Twilio account with WhatsApp access can receive messages.

### 4.2 Message Format

WhatsApp only permits pre-approved message templates. Sending non-approved templates may result in account restrictions.

## 5. SMS

Version 13 introduced SMS as an alert channel. Complete SMS Settings configuration to use this channel.

## 6. Related Topics

- SMS Settings
- Document Follow

## 7. One-Off Reminders

One-off reminders are available in the nightly version. To set a reminder:

1. Open the document
2. Click the menu (three dots) and select "Remind Me"
3. Select a time and add a description
4. Click "Create"

The system sends a system notification at the configured time with your reminder description.
