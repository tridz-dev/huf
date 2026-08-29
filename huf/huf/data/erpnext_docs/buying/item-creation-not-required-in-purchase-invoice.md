---
title: "Purchase invoice for Services"
source_url: "https://docs.frappe.io/erpnext/item-creation-not-required-in-purchase-invoice"
section: buying
---

# Purchase invoice for Services

## Overview

This guide explains how to create a purchase invoice for services in ERPNext, a process that involves setting up suppliers, creating service items, and documenting the transaction.

## Step-by-Step Process

### 1. Set Up Supplier

Begin by accessing the supplier management section:

* Navigate to **Buying > Supplier**
* Click **New** to create a fresh supplier record
* Input the supplier's name, contact details, and address information
* Save the completed supplier record

### 2. Create a Service Item

Establish a service item in your system:

* Go to **Stock > Item**
* Click **New** to start a new item entry
* Enter an item code and descriptive name
* Select or establish an item group designated for services
* Set **Item Type** to **Service**
* Add relevant details like unit of measure and service description
* Save the item record

### 3. Create a Purchase Invoice

Document the service purchase:

* Access **Buying > Purchase Invoice**
* Click **New** to begin a fresh invoice
* Complete basic information including the supplier selection, invoice date, and any supplier reference numbers
* In the items section, click **Add Item** and select your service item
* Provide a detailed service description
* Enter the rate and quantity for the service
* Include any applicable taxes or charges in the designated section
* Configure the appropriate expense account under the **Accounts** section
* Review all details for accuracy and click **Save**

### 4. Submit

Finalize the invoice:

* Click **Submit** to complete and lock the invoice record
