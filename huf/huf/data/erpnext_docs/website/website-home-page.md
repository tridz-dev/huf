---
title: "Website Home Page"
source_url: "https://docs.frappe.io/erpnext/website-home-page"
section: website
---

# Website Home Page

It is indeed possible in ERPNext to designate a standard page as your default website home page. Here are the steps to configure this:

## Step 1: Create a Web Page
Navigate to `Website > Web Site > Web Page` and select the `New` button.

* Enter the page title
* Specify a route in lowercase characters
* Insert content into the `Main Content` section, using markdown if needed for complexity
* Enable the `Published` checkbox
* Click `Save`

## Step 2: Open Website Settings Page
Go to `Website > Setup > Website Settings`

## Step 3: Set Home page

Copy the `route` value from your web page and paste it into the `Home Page` field. This action configures ERPNext to treat this route as `/index` for your site.

![Website Setting Home](/files/Selection_021.png)

## Step 4: Save Website Settings Form

Click the `Save` button on the website settings page and refresh your system through the Help menu. Using this process, you can designate any standard page as your website's default landing page, ensuring visitors encounter this page upon arrival.
