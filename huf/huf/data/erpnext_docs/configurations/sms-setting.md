---
title: "SMS Settings"
source_url: "https://docs.frappe.io/erpnext/sms-setting"
section: configurations
---

# SMS Settings

You can subscribe to an SMS provider to send SMS to mobile numbers.

To integrate SMS in ERPNext, approach an SMS Gateway Provider who provides HTTP API. They will create an account for you and will provide a unique username and password.

To access SMS settings, go to:
> Home > Settings > SMS Settings

To configure SMS Settings in ERPNext, find out their HTTP API (a document which describes the method of accessing their SMS interface from 3rd party applications). In this document, you will get a URL which is used to send the SMS using HTTP request. Using this URL, you can configure SMS Settings in ERPNext.

Example SMS Gateway URL:

```
http://instant.smses.com/web2sms.php?username=<username>&password=<password>&to=<mobilenumber>&sender=<senderid>&message=<message>
```

> Note: For SMS Gateway URL, only include the string before the "?".

Example:

```
http://instant.smses.com/web2sms.php?username=abcd&password=abcd&to=9900XXXXXX&sender=DEMO&message=THIS+IS+A+TEST+SMS
```

The above URL will send SMS from account abcd to mobile number 9900XXXXXX with sender ID as DEMO with a text message as "THIS IS A TEST SMS".

Note that some parameters in the URL are static. You will get static values from your SMS Provider like username, password, etc. These static values should be entered in the Static Parameters table.

## How to configure ERPNext with Voip.ms

The first step is to login to voip.ms account. Then go **Main menu**, **SOAP and REST/JSON API**. Enable the API, set a password and whitelist your server ip address.

Then go to DIDs and enable SMS on the number SMS will be sent from.

Set SMS Gateway to **https://voip.ms/api/v1/rest.php**

Set Message Parameter to **message**

Receiver Parameter to **dst**

Create 4 new Static Parameters:

- **api_username** (voip.ms account username)
- **api_password** (the API password configured few minutes ago)
- **method** set value to **sendSMS**
- **did** (the 10 digits DID that will be used to send the sms)

Then go to SMS Center to test if everything works properly.

### Related Topics
1. [Email Account](/erpnext/email-account)
2. [Notifications](/erpnext/notifications)
