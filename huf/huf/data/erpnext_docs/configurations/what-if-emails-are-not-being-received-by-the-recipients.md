---
title: "What if Emails are not being received by the Recipients?"
source_url: "https://docs.frappe.io/erpnext/what-if-emails-are-not-being-received-by-the-recipients"
section: configurations
---

# What if Emails are not being received by the Recipients?

When an Email is sent, you assume that the Email will be received by the Recipient, but if you receive a feedback that they haven't received the Email, following are the steps to troubleshoot:

1) Sending an Email to an Email address that is misspelled or does not exist results in that Email not being delivered. While it seems obvious, it is easily overlooked and happens often.

2) The second thing you can do to check is to send an Email to yourself, this can be done via creating a New Communication.

*Go to Communication List > Click on New.*

3) If the above method fails, kindly configure your Email Account again.

*Go to Email Account > Open the Email to check > if as per you everything is correct, click on Save. It will throw an error if there is any issue with the Configuration and you can rectify it accordingly.*

4) Check Email Queues for the unsent messages or errors if any.

*If the state is Error(as in the screenshot below), you can find the error cause by opening that email and scroll down to Error field to know the error.*

![](/files/lNVCy3g.png)

![](/files/NJJmwTX.png)

***NOTE: The error can differ from what can be seen in the above screenshot.***
